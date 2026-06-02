from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from typing import Callable


@dataclass
class ActionResult:
    success: bool
    cancelled: bool   # True when pkexec auth was rejected (exit 126/127)
    stderr: str


class PackageActionBackend:
    TIMEOUT = 120

    def reinstall(self, pkg_name: str, line_cb=None) -> ActionResult:
        return self._run_streaming(
            ["pkexec", "apt", "install", "--reinstall", "-y", pkg_name], line_cb)

    def reinstall_reset(self, pkg_name: str, line_cb=None) -> ActionResult:
        script = f"apt purge -y {pkg_name} && apt install -y {pkg_name}"
        return self._run_streaming(["pkexec", "bash", "-c", script], line_cb)

    def uninstall(self, pkg_name: str, purge: bool, line_cb=None) -> ActionResult:
        verb = "purge" if purge else "remove"
        return self._run_streaming(["pkexec", "apt", verb, "-y", pkg_name], line_cb)

    def reinstall_batch(self, pkg_names: list[str], line_cb=None) -> ActionResult:
        quoted = " ".join(shlex.quote(n) for n in pkg_names)
        return self._run_streaming(
            ["pkexec", "bash", "-c", f"apt install --reinstall -y {quoted}"], line_cb)

    def reinstall_reset_batch(self, pkg_names: list[str], line_cb=None) -> ActionResult:
        quoted = " ".join(shlex.quote(n) for n in pkg_names)
        script = f"apt purge -y {quoted} && apt install -y {quoted}"
        return self._run_streaming(["pkexec", "bash", "-c", script], line_cb)

    def uninstall_batch(self, pkg_names: list[str], purge: bool,
                        line_cb=None) -> ActionResult:
        verb = "purge" if purge else "remove"
        quoted = " ".join(shlex.quote(n) for n in pkg_names)
        return self._run_streaming(
            ["pkexec", "bash", "-c", f"apt {verb} -y {quoted}"], line_cb)

    # ── Flatpak single-package actions ────────────────────────────────────────

    def reinstall_flatpak(self, app_id: str, line_cb=None) -> ActionResult:
        return self._run_streaming(
            ["pkexec", "flatpak", "install", "--noninteractive", "--reinstall", app_id],
            line_cb)

    def reinstall_reset_flatpak(self, app_id: str, line_cb=None) -> ActionResult:
        q = shlex.quote(app_id)
        script = (f"flatpak uninstall --noninteractive --delete-data {q} "
                  f"&& flatpak install --noninteractive {q}")
        return self._run_streaming(["pkexec", "bash", "-c", script], line_cb)

    def uninstall_flatpak(self, app_id: str, delete_data: bool,
                          line_cb=None) -> ActionResult:
        if delete_data:
            return self._run_streaming(
                ["pkexec", "flatpak", "uninstall", "--noninteractive",
                 "--delete-data", app_id], line_cb)
        return self._run_streaming(
            ["pkexec", "flatpak", "uninstall", "--noninteractive", app_id], line_cb)

    # ── Flatpak batch actions ─────────────────────────────────────────────────

    def reinstall_flatpak_batch(self, app_ids: list[str], line_cb=None) -> ActionResult:
        quoted = " ".join(shlex.quote(a) for a in app_ids)
        return self._run_streaming(
            ["pkexec", "bash", "-c",
             f"flatpak install --noninteractive --reinstall {quoted}"], line_cb)

    def reinstall_reset_flatpak_batch(self, app_ids: list[str],
                                      line_cb=None) -> ActionResult:
        quoted = " ".join(shlex.quote(a) for a in app_ids)
        script = (f"flatpak uninstall --noninteractive --delete-data {quoted} "
                  f"&& flatpak install --noninteractive {quoted}")
        return self._run_streaming(["pkexec", "bash", "-c", script], line_cb)

    def uninstall_flatpak_batch(self, app_ids: list[str], delete_data: bool,
                                line_cb=None) -> ActionResult:
        quoted = " ".join(shlex.quote(a) for a in app_ids)
        if delete_data:
            return self._run_streaming(
                ["pkexec", "bash", "-c",
                 f"flatpak uninstall --noninteractive --delete-data {quoted}"], line_cb)
        return self._run_streaming(
            ["pkexec", "bash", "-c",
             f"flatpak uninstall --noninteractive {quoted}"], line_cb)

    # ── Update actions ────────────────────────────────────────────────────────

    def update_apt(self, pkg_name: str, line_cb=None) -> ActionResult:
        return self._run_streaming(
            ["pkexec", "apt", "install", "--only-upgrade", "-y", pkg_name], line_cb)

    def update_all_apt(self, pkg_names: list[str], line_cb=None) -> ActionResult:
        quoted = " ".join(shlex.quote(n) for n in pkg_names)
        return self._run_streaming(
            ["pkexec", "bash", "-c", f"apt install --only-upgrade -y {quoted}"], line_cb)

    def update_flatpak(self, app_id: str, line_cb=None) -> ActionResult:
        return self._run_streaming(
            ["pkexec", "flatpak", "update", "--noninteractive", app_id], line_cb)

    def update_all_flatpak(self, app_ids: list[str], line_cb=None) -> ActionResult:
        quoted = " ".join(shlex.quote(a) for a in app_ids)
        return self._run_streaming(
            ["pkexec", "bash", "-c",
             f"flatpak update --noninteractive {quoted}"], line_cb)

    # ── Version rollback actions ──────────────────────────────────────────────

    def install_apt_version(self, pkg_name: str, version: str,
                            line_cb=None) -> ActionResult:
        return self._run_streaming(
            ["pkexec", "apt", "install", "-y", f"{pkg_name}={version}"], line_cb)

    def install_flatpak_commit(self, app_id: str, commit: str,
                               line_cb=None) -> ActionResult:
        return self._run_streaming(
            ["pkexec", "flatpak", "update", "--noninteractive",
             f"--commit={commit}", app_id], line_cb)

    # ── Core streaming runner ─────────────────────────────────────────────────

    def _run_streaming(self, cmd: list[str], line_cb=None) -> ActionResult:
        """Run cmd, stream stdout+stderr merged, call line_cb per line.

        Returns ActionResult based on process exit code.
        Accumulated output is returned as ActionResult.stderr on failure.
        """
        collected: list[str] = []
        try:
            with subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            ) as proc:
                if proc.stdout:
                    for line in proc.stdout:
                        stripped = line.rstrip("\n")
                        collected.append(stripped)
                        if line_cb:
                            line_cb(stripped)
        except subprocess.TimeoutExpired:
            return ActionResult(
                success=False, cancelled=False,
                stderr=f"Command timed out after {self.TIMEOUT} seconds.",
            )
        except FileNotFoundError:
            return ActionResult(
                success=False, cancelled=False,
                stderr="pkexec is not available on this system.",
            )
        except Exception as exc:
            return ActionResult(success=False, cancelled=False, stderr=str(exc))

        rc = proc.returncode  # set by Popen.__exit__ → proc.wait()

        # pkexec exit 126 = not authorised; 127 = pkexec itself not found
        if rc in (126, 127):
            return ActionResult(success=False, cancelled=True, stderr="")

        if rc != 0:
            return ActionResult(
                success=False, cancelled=False,
                stderr="\n".join(collected),
            )

        return ActionResult(success=True, cancelled=False, stderr="")
