"""
Audio utility functions for format conversion.
Handles mulaw, PCM, WAV conversions for telephony.
"""

import struct
from typing import Tuple
import io


class AudioConverter:
    """
    Audio format converter for telephony integration.
    
    Twilio uses mulaw at 8kHz, while our AI services
    typically use PCM at 16kHz or higher.
    """
    
    # Mulaw encoding table
    MULAW_BIAS = 132
    MULAW_MAX = 32635
    MULAW_TABLE = None
    
    @classmethod
    def _init_mulaw_table(cls):
        """Initialize mulaw encoding lookup table."""
        if cls.MULAW_TABLE is not None:
            return
        
        cls.MULAW_TABLE = [0] * 256
        for i in range(256):
            # Decode mulaw to linear
            mu = ~i
            sign = mu & 0x80
            exponent = (mu >> 4) & 0x07
            mantissa = mu & 0x0F
            sample = ((mantissa << 3) + 0x84) << exponent
            sample -= 0x84
            cls.MULAW_TABLE[i] = -sample if sign else sample
    
    @staticmethod
    def pcm_to_mulaw(pcm_data: bytes, sample_width: int = 2) -> bytes:
        """
        Convert PCM audio to mulaw format.
        
        Args:
            pcm_data: Raw PCM audio bytes
            sample_width: Bytes per sample (2 for 16-bit)
        
        Returns:
            Mulaw encoded audio
        """
        if sample_width != 2:
            raise ValueError("Only 16-bit PCM supported")
        
        samples = struct.unpack(f"<{len(pcm_data) // 2}h", pcm_data)
        mulaw_bytes = bytearray()
        
        for sample in samples:
            # Bias
            sample = sample + AudioConverter.MULAW_BIAS
            
            # Clip
            if sample < 0:
                sample = -sample
                sign = 0x80
            else:
                sign = 0
            
            if sample > AudioConverter.MULAW_MAX:
                sample = AudioConverter.MULAW_MAX
            
            # Find exponent and mantissa
            exponent = 7
            exp_mask = 0x4000
            while exponent > 0 and not (sample & exp_mask):
                exponent -= 1
                exp_mask >>= 1
            
            mantissa = (sample >> (exponent + 3)) & 0x0F
            mulaw_byte = ~(sign | (exponent << 4) | mantissa) & 0xFF
            mulaw_bytes.append(mulaw_byte)
        
        return bytes(mulaw_bytes)
    
    @staticmethod
    def mulaw_to_pcm(mulaw_data: bytes) -> bytes:
        """
        Convert mulaw audio to PCM format.
        
        Args:
            mulaw_data: Mulaw encoded audio
        
        Returns:
            16-bit PCM audio
        """
        AudioConverter._init_mulaw_table()
        
        samples = []
        for byte in mulaw_data:
            samples.append(AudioConverter.MULAW_TABLE[byte])
        
        return struct.pack(f"<{len(samples)}h", *samples)
    
    @staticmethod
    def resample(
        audio_data: bytes,
        from_rate: int,
        to_rate: int,
        sample_width: int = 2,
    ) -> bytes:
        """
        Resample audio to a different sample rate.
        
        Uses simple linear interpolation.
        For production, consider using scipy or librosa.
        
        Args:
            audio_data: Raw audio bytes
            from_rate: Source sample rate
            to_rate: Target sample rate
            sample_width: Bytes per sample
        
        Returns:
            Resampled audio data
        """
        if from_rate == to_rate:
            return audio_data
        
        # Unpack samples
        num_samples = len(audio_data) // sample_width
        if sample_width == 2:
            samples = list(struct.unpack(f"<{num_samples}h", audio_data))
        else:
            raise ValueError("Only 16-bit audio supported")
        
        # Calculate new length
        new_length = int(num_samples * to_rate / from_rate)
        
        # Linear interpolation
        new_samples = []
        for i in range(new_length):
            src_idx = i * from_rate / to_rate
            idx_low = int(src_idx)
            idx_high = min(idx_low + 1, num_samples - 1)
            frac = src_idx - idx_low
            
            sample = int(samples[idx_low] * (1 - frac) + samples[idx_high] * frac)
            new_samples.append(sample)
        
        return struct.pack(f"<{len(new_samples)}h", *new_samples)
    
    @staticmethod
    def create_wav_header(
        sample_rate: int,
        num_channels: int,
        bits_per_sample: int,
        data_size: int,
    ) -> bytes:
        """
        Create a WAV file header.
        
        Args:
            sample_rate: Sample rate in Hz
            num_channels: Number of channels (1=mono, 2=stereo)
            bits_per_sample: Bits per sample (8, 16, 24, 32)
            data_size: Size of audio data in bytes
        
        Returns:
            44-byte WAV header
        """
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        
        header = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF',
            36 + data_size,
            b'WAVE',
            b'fmt ',
            16,  # Subchunk1 size (PCM)
            1,   # Audio format (1 = PCM)
            num_channels,
            sample_rate,
            byte_rate,
            block_align,
            bits_per_sample,
            b'data',
            data_size,
        )
        
        return header
    
    @staticmethod
    def wrap_in_wav(
        pcm_data: bytes,
        sample_rate: int = 16000,
        channels: int = 1,
        bits: int = 16,
    ) -> bytes:
        """
        Wrap raw PCM data in WAV container.
        
        Args:
            pcm_data: Raw PCM audio
            sample_rate: Sample rate
            channels: Number of channels
            bits: Bits per sample
        
        Returns:
            Complete WAV file bytes
        """
        header = AudioConverter.create_wav_header(
            sample_rate, channels, bits, len(pcm_data)
        )
        return header + pcm_data
    
    @staticmethod
    def strip_wav_header(wav_data: bytes) -> Tuple[bytes, dict]:
        """
        Remove WAV header and return raw audio + metadata.
        
        Args:
            wav_data: Complete WAV file
        
        Returns:
            Tuple of (raw_audio, metadata_dict)
        """
        if len(wav_data) < 44:
            raise ValueError("Invalid WAV file")
        
        # Parse header
        riff, size, wave = struct.unpack('<4sI4s', wav_data[:12])
        
        if riff != b'RIFF' or wave != b'WAVE':
            raise ValueError("Not a valid WAV file")
        
        # Find data chunk
        pos = 12
        while pos < len(wav_data) - 8:
            chunk_id, chunk_size = struct.unpack('<4sI', wav_data[pos:pos+8])
            
            if chunk_id == b'fmt ':
                fmt_data = wav_data[pos+8:pos+8+chunk_size]
                audio_format, num_channels, sample_rate, byte_rate, block_align, bits_per_sample = struct.unpack(
                    '<HHIIHH', fmt_data[:16]
                )
            elif chunk_id == b'data':
                audio_data = wav_data[pos+8:pos+8+chunk_size]
                return audio_data, {
                    "sample_rate": sample_rate,
                    "channels": num_channels,
                    "bits_per_sample": bits_per_sample,
                }
            
            pos += 8 + chunk_size
        
        raise ValueError("No data chunk found in WAV file")
    
    @staticmethod
    def adjust_volume(audio_data: bytes, factor: float) -> bytes:
        """
        Adjust audio volume.
        
        Args:
            audio_data: 16-bit PCM audio
            factor: Volume multiplier (1.0 = unchanged)
        
        Returns:
            Adjusted audio data
        """
        samples = struct.unpack(f"<{len(audio_data) // 2}h", audio_data)
        adjusted = [max(-32768, min(32767, int(s * factor))) for s in samples]
        return struct.pack(f"<{len(adjusted)}h", *adjusted)
