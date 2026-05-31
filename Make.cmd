@echo off
REM bg-mcpcore — Windows command dispatcher (mirrors the Makefile targets).
REM Usage: Make.cmd <target>   e.g.  Make.cmd test

setlocal
set TARGET=%1
if "%TARGET%"=="" set TARGET=help

if /I "%TARGET%"=="install"     ( pip install -e . & goto :eof )
if /I "%TARGET%"=="install-dev" ( pip install -e ".[dev,docs,openapi,redis,tasks,testkit]" && pre-commit install & goto :eof )
if /I "%TARGET%"=="lint"        ( ruff check src/ tests/ & goto :eof )
if /I "%TARGET%"=="format"      ( ruff check --fix src/ tests/ & goto :eof )
if /I "%TARGET%"=="type-check"  ( mypy src/bg_mcpcore/ & goto :eof )
if /I "%TARGET%"=="test"        ( pytest & goto :eof )
if /I "%TARGET%"=="test-cov"    ( pytest --cov=src/bg_mcpcore --cov-report=term-missing --cov-report=html & goto :eof )
if /I "%TARGET%"=="build"       ( python -m build & goto :eof )
if /I "%TARGET%"=="pre-commit"  ( pre-commit run --all-files & goto :eof )
if /I "%TARGET%"=="all-checks"  ( ruff check src/ tests/ && mypy src/bg_mcpcore/ && pytest & goto :eof )

echo bg-mcpcore commands: install install-dev lint format type-check test test-cov build pre-commit all-checks
endlocal
