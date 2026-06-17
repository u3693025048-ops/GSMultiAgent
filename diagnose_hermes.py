#!/usr/bin/env python3
"""
Hermes Agent 诊断脚本
检查Hermes依赖和导入是否正常
"""

import sys
import subprocess

def check_module(module_name, package_name=None):
    """检查模块是否可导入"""
    package_name = package_name or module_name
    try:
        __import__(module_name)
        print(f"✅ {module_name:30} - OK")
        return True
    except ImportError as e:
        print(f"❌ {module_name:30} - FAILED: {e}")
        print(f"   → 尝试安装: pip install {package_name}")
        return False

def check_pip_package(package_name):
    """检查pip中是否安装了包"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", package_name],
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8',
            errors='ignore'  # 忽略编码错误
        )
        if result.returncode == 0:
            print(f"✅ pip: {package_name:30} - INSTALLED")
            return True
        else:
            print(f"❌ pip: {package_name:30} - NOT INSTALLED")
            return False
    except Exception as e:
        print(f"⚠️  pip: {package_name:30} - CHECK FAILED: {e}")
        return False

def main():
    print("=" * 70)
    print("Hermes Agent 诊断工具")
    print("=" * 70)
    
    print("\n[1] 检查核心Hermes模块...")
    print("-" * 70)
    hermes_modules = [
        ("run_agent", "hermes-agent"),
        ("tools.registry", "hermes-agent"),
        ("model_tools", "model-tools"),
        ("asyncio", "asyncio"),  # 标准库
    ]
    
    hermes_ok = all(check_module(m, p) for m, p in hermes_modules)
    
    print("\n[2] 检查pip中的包...")
    print("-" * 70)
    packages = [
        "hermes-agent",
        "run-agent",
        "model-tools",
        "openai",
    ]
    
    for pkg in packages:
        check_pip_package(pkg)
    
    print("\n[3] 检查GSMultiAgent集成...")
    print("-" * 70)
    try:
        from multi_agent.integration.hermes_integration import HERMES_AVAILABLE, HermesIntegration
        print(f"✅ hermes_integration.py - OK")
        print(f"   HERMES_AVAILABLE: {HERMES_AVAILABLE}")
        print(f"   HermesIntegration: {HermesIntegration}")
    except Exception as e:
        print(f"❌ hermes_integration.py - FAILED: {e}")
    
    print("\n[4] 检查LLM配置...")
    print("-" * 70)
    try:
        from multi_agent.config_loader import get_config
        cfg = get_config()
        llm_cfg = cfg.llm
        print(f"✅ config.yaml - OK")
        print(f"   model: {llm_cfg.model}")
        print(f"   provider: {llm_cfg.provider}")
        print(f"   api_key: {'***' if llm_cfg.api_key else '(empty)'}")
        print(f"   base_url: {llm_cfg.base_url or '(default)'}")
    except Exception as e:
        print(f"❌ config.yaml - FAILED: {e}")
    
    print("\n" + "=" * 70)
    print("诊断结果")
    print("=" * 70)
    
    if hermes_ok:
        print("✅ Hermes依赖完整，应该可以正常工作")
        print("\n建议：运行 CLI 测试")
        print("  python cli_agent.py --prompt \"T4工况，要求命中率>=92%，SEP<=7m\"")
    else:
        print("❌ Hermes依赖不完整，需要安装缺失的包")
        print("\n建议：")
        print("  1. 安装Hermes Agent:")
        print("     pip install hermes-agent")
        print("  2. 或安装所有依赖:")
        print("     pip install -r requirements.txt")
        print("  3. 然后重新运行诊断:")
        print("     python diagnose_hermes.py")

if __name__ == "__main__":
    main()
