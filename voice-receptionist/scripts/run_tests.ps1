#!/usr/bin/env pwsh
# ===========================================
# Voice AI Test Runner
# ===========================================
# Usage: .\scripts\run_tests.ps1 [test_type]
# Types: all, unit, integration, health

param(
    [string]$TestType = "all"
)

$ErrorActionPreference = "Stop"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Voice AI Test Runner" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

function Test-Health {
    Write-Host "Running Health Checks..." -ForegroundColor Yellow
    
    # Basic health
    Write-Host "  [1/3] Basic health endpoint..." -ForegroundColor Gray
    try {
        $resp = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method GET
        if ($resp.status -eq "ok") {
            Write-Host "  ✅ Basic health: OK" -ForegroundColor Green
        } else {
            Write-Host "  ❌ Basic health: FAILED" -ForegroundColor Red
        }
    } catch {
        Write-Host "  ❌ Basic health: API not responding" -ForegroundColor Red
        Write-Host "     Make sure the server is running: docker compose up -d" -ForegroundColor Gray
        return
    }
    
    # Detailed health
    Write-Host "  [2/3] Detailed health checks..." -ForegroundColor Gray
    try {
        $resp = Invoke-RestMethod -Uri "http://localhost:8000/health/detailed" -Method GET
        foreach ($check in $resp.checks.PSObject.Properties) {
            $status = $check.Value.status
            $icon = if ($status -eq "healthy") { "✅" } elseif ($status -eq "not_configured") { "⚠️" } else { "❌" }
            Write-Host "  $icon $($check.Name): $status" -ForegroundColor $(if ($status -eq "healthy") { "Green" } elseif ($status -eq "not_configured") { "Yellow" } else { "Red" })
        }
    } catch {
        Write-Host "  ⚠️ Detailed health endpoint not available" -ForegroundColor Yellow
    }
    
    # API docs
    Write-Host "  [3/3] API documentation..." -ForegroundColor Gray
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:8000/docs" -Method GET
        if ($resp.StatusCode -eq 200) {
            Write-Host "  ✅ API docs: Available at http://localhost:8000/docs" -ForegroundColor Green
        }
    } catch {
        Write-Host "  ⚠️ API docs not available (may be disabled in production)" -ForegroundColor Yellow
    }
    
    Write-Host ""
}

function Test-Unit {
    Write-Host "Running Unit Tests..." -ForegroundColor Yellow
    
    if (Test-Path "tests/test_unit.py") {
        python -m pytest tests/test_unit.py -v --tb=short
    } else {
        Write-Host "  No unit tests found" -ForegroundColor Gray
    }
    
    Write-Host ""
}

function Test-Integration {
    Write-Host "Running Integration Tests..." -ForegroundColor Yellow
    Write-Host "  (Requires server to be running)" -ForegroundColor Gray
    
    if (Test-Path "tests/test_integration.py") {
        python -m pytest tests/test_integration.py -v --tb=short --asyncio-mode=auto
    } else {
        Write-Host "  No integration tests found" -ForegroundColor Gray
    }
    
    Write-Host ""
}

function Test-All {
    Test-Health
    Test-Unit
    Test-Integration
}

# Main
Write-Host "Test Type: $TestType" -ForegroundColor Gray
Write-Host ""

switch ($TestType.ToLower()) {
    "health" { Test-Health }
    "unit" { Test-Unit }
    "integration" { Test-Integration }
    "all" { Test-All }
    default {
        Write-Host "Unknown test type: $TestType" -ForegroundColor Red
        Write-Host "Available: all, unit, integration, health" -ForegroundColor Gray
    }
}

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Testing Complete" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
