from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "apps" / "mobile"
ANDROID = MOBILE / "android"


def command(name: str) -> str:
    return f"{name}.cmd" if os.name == "nt" else name


def project_python() -> str:
    candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def android_env() -> dict[str, str]:
    env = os.environ.copy()
    if os.name == "nt":
        env["JAVA_HOME"] = r"C:\Program Files\Android\Android Studio\jbr"
        env["ANDROID_HOME"] = r"C:\Users\jthol\AppData\Local\Android\Sdk"
    else:
        env.setdefault("JAVA_HOME", r"C:\Program Files\Android\Android Studio\jbr")
        env.setdefault("ANDROID_HOME", r"C:\Users\jthol\AppData\Local\Android\Sdk")
    env.setdefault("ANDROID_SDK_ROOT", env["ANDROID_HOME"])
    env["PATH"] = os.pathsep.join(
        [
            str(Path(env["JAVA_HOME"]) / "bin"),
            str(Path(env["ANDROID_HOME"]) / "platform-tools"),
            str(Path.home() / ".maestro" / "maestro" / "bin"),
            env.get("PATH", ""),
        ]
    )
    return env


def maestro_command() -> str:
    binary = "maestro.bat" if os.name == "nt" else "maestro"
    candidates = [
        Path.home() / ".maestro" / "maestro" / "bin" / binary,
        Path.home() / ".maestro" / "bin" / binary,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return command("maestro")


def run(label: str, cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    print(f"\n=== {label} ===", flush=True)
    subprocess.run(cmd, cwd=str(cwd), env=env, check=True)


def verify_backend() -> None:
    python = project_python()
    run("backend unit tests", [python, "-m", "pytest", "services/control_api/tests", "-m", "unit", "-v"], ROOT)
    run(
        "backend integration tests",
        [python, "-m", "pytest", "services/control_api/tests", "-m", "integration", "-v"],
        ROOT,
    )
    run("backend e2e tests", [python, "-m", "pytest", "services/control_api/tests", "-m", "e2e", "-v"], ROOT)


def verify_mobile() -> None:
    npm = command("npm")
    npx = command("npx")
    run("mobile TypeScript", [npm, "run", "typecheck"], MOBILE)
    run("mobile unit tests", [npm, "run", "test:unit"], MOBILE)
    run("Expo config", [npx, "expo", "config", "--type", "public"], MOBILE)


def verify_android(*, sideload: bool) -> None:
    env = android_env()
    gradlew = ANDROID / ("gradlew.bat" if os.name == "nt" else "gradlew")
    apk = ANDROID / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
    run("Android release APK", [str(gradlew), "assembleRelease"], ANDROID, env)
    if not apk.exists() or apk.stat().st_size < 10_000_000:
        raise SystemExit(f"Release APK missing or unexpectedly small: {apk}")
    print(f"Release APK OK: {apk} ({apk.stat().st_size} bytes)")
    if not sideload:
        return

    adb = Path(env["ANDROID_HOME"]) / "platform-tools" / "adb.exe"
    if not adb.exists():
        raise SystemExit(f"adb not found: {adb}")
    run("ADB devices", [str(adb), "devices"], ANDROID, env)
    run("sideload release APK", [str(adb), "install", "-r", str(apk)], ANDROID, env)
    subprocess.run([str(adb), "logcat", "-c"], env=env, check=True)
    subprocess.run([str(adb), "shell", "am", "force-stop", "com.anonymous.hermesmobilecontrol"], env=env, check=True)
    run(
        "launch installed app",
        [str(adb), "shell", "am", "start", "-n", "com.anonymous.hermesmobilecontrol/.MainActivity"],
        ANDROID,
        env,
    )
    subprocess.run([sys.executable, "-c", "import time; time.sleep(5)"], check=True)
    pid = subprocess.run(
        [str(adb), "shell", "pidof", "com.anonymous.hermesmobilecontrol"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    ).stdout.strip()
    if not pid:
        raise SystemExit("App process is not running after launch")
    log = subprocess.run(
        [str(adb), "logcat", "-d", "-v", "time", "-t", "1200"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    ).stdout
    markers = ["FATAL EXCEPTION", "Process: com.anonymous.hermesmobilecontrol", "Unable to load script"]
    if any(marker in log for marker in markers):
        raise SystemExit("Android launch failure marker found in logcat")
    print(f"Android app running pid: {pid}")


def verify_maestro() -> None:
    env = android_env()
    env.setdefault("MAESTRO_CLI_NO_ANALYTICS", "true")
    env.setdefault("MAESTRO_CLI_ANALYSIS_NOTIFICATION_DISABLED", "true")
    for flow in [".maestro/smoke.yaml", ".maestro/settings.yaml", ".maestro/new-task.yaml"]:
        run(f"Maestro UI flow: {flow}", [maestro_command(), "test", flow], ROOT, env)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Hermes Mobile Control layers.")
    parser.add_argument("--android", action="store_true", help="also build the Android release APK")
    parser.add_argument("--sideload", action="store_true", help="install and launch the release APK on a connected device")
    parser.add_argument("--maestro", action="store_true", help="run the Maestro UI smoke flow on a connected Android device")
    args = parser.parse_args()

    verify_backend()
    verify_mobile()
    if args.android or args.sideload or args.maestro:
        verify_android(sideload=args.sideload or args.maestro)
    if args.maestro:
        verify_maestro()
    print("\nCANONICAL VERIFICATION PASSED")


if __name__ == "__main__":
    main()
