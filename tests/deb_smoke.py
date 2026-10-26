"""Validate the installer payload and desktop identity without installing it."""
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import tempfile

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QImage
from bundle_smoke import PackagedApp, ROOT


def main():
    app = QCoreApplication.instance() or QCoreApplication([])
    package = ROOT / 'dist/khana_0.4.0-1_amd64.deb'
    fields = subprocess.check_output(['dpkg-deb', '--field', str(package)], text=True)
    assert 'Package: khana\n' in fields and 'Architecture: amd64\n' in fields
    with tempfile.TemporaryDirectory(prefix='khana-deb-') as temporary:
        folder = Path(temporary)
        payload = folder / 'payload'
        subprocess.run(['dpkg-deb', '--extract', str(package), str(payload)], check=True)
        subprocess.run(['dpkg-deb', '--control', str(package), str(folder / 'control')], check=True)
        subprocess.run(['md5sum', '--check', '--quiet', str(folder / 'control/md5sums')], cwd=payload, check=True)
        assert sorted(p.name for p in (folder / 'control').iterdir()) == ['control', 'md5sums']
        entry = payload / 'usr/share/applications/io.khana.Khana.desktop'
        subprocess.run(['desktop-file-validate', str(entry)], check=True)
        assert (payload / 'usr/bin/khana').readlink() == Path('/opt/khana/Khana')
        executable = payload / 'opt/khana/Khana'
        assert subprocess.check_output([str(executable), '--version'], text=True).strip() == 'Khana 0.4.0'
        for size in (16, 22, 24, 32, 48, 64, 128, 256, 512):
            icon = QImage(str(payload / f'usr/share/icons/hicolor/{size}x{size}/apps/io.khana.Khana.png'))
            assert icon.width() == size and icon.height() == size
            assert icon.hasAlphaChannel()
        print('PASS: installer metadata, payload hashes, command, version and all logo sizes', flush=True)

        # Only the fixture's Exec/TryExec paths are relocated. The real package
        # always registers /usr/bin/khana. No host menu/config is modified.
        data = folder / 'xdg-data'
        shutil.copytree(payload / 'usr/share/icons', data / 'icons')
        applications = data / 'applications'; applications.mkdir(parents=True)
        (applications / entry.name).write_text(entry.read_text().replace('/usr/bin/khana', str(executable)))
        subprocess.run(['update-desktop-database', str(applications)], check=True)
        env = {**os.environ, 'XDG_DATA_HOME': str(data), 'XDG_CONFIG_HOME': str(folder / 'registry-config')}
        result = subprocess.check_output(['/usr/bin/python3', str(ROOT / 'tests/desktop_registration.py'), str(data)], env=env, text=True)
        print('PASS: GNOME search finds Khana, resolves the installed logo and matches the desktop class:', result.strip(), flush=True)

        running = None
        try:
            running = PackagedApp(executable, folder, extra_env={'WAYLAND_DEBUG': 'client'})
            assert running.evaluate("document.querySelector('.version-note').textContent.includes('0.4')")
            running.close()
            if os.environ.get('XDG_SESSION_TYPE') == 'wayland':
                assert 'set_app_id("io.khana.Khana")' in (folder / 'app.log').read_text()
                print('PASS: actual Wayland app ID matches the installable desktop entry', flush=True)
            # Exercise SQLite and the annotation UI in the frozen executable,
            # including a full process restart with the same user configuration.
            source = folder / 'reading.md'
            original = '# Reading\n\nA place to remember.\n\nیادداشت روی متن فارسی و English.\n'
            source.write_text(original)
            running = PackagedApp(executable, folder, [source])
            running.evaluate("document.getElementById('star-document').click()")
            running.wait("document.getElementById('star-document').getAttribute('aria-pressed')==='true'", 'packaged library saves favorites')
            running.evaluate("document.querySelector('[data-reading-block=\"1\"] .annotation-tools button').click(); document.getElementById('annotation-name').value='Checkpoint'; document.getElementById('annotation-save').click()")
            running.wait("!document.getElementById('annotation-dialog').open && document.getElementById('annotation-count').textContent==='1'", 'packaged app saves a reading mark')
            running.evaluate("document.querySelector('[data-reading-block=\"2\"] .annotation-tools button:last-child').click(); document.getElementById('annotation-name').value='Thoughts'")
            running.evaluate('document.getElementById("annotation-body").value=' + json.dumps('یادداشت من\nEnglish note'))
            running.evaluate("document.getElementById('annotation-save').click()")
            running.wait("!document.getElementById('annotation-dialog').open && document.getElementById('annotation-count').textContent==='2'", 'packaged app saves a mixed-language note')
            running.close()
            running = PackagedApp(executable, folder)
            running.wait("document.getElementById('annotation-count').textContent==='2' && document.querySelectorAll('.annotation-badge').length===2", 'documents, marks and notes survive an executable restart')
            assert running.evaluate("document.getElementById('star-document').getAttribute('aria-pressed')==='true'")
            running.evaluate("document.getElementById('annotations-button').click(); document.querySelectorAll('.annotation-actions button:last-child')[1].click()")
            running.wait("document.getElementById('annotation-count').textContent==='1'", 'packaged app deletes a note')
            running.evaluate("document.querySelector('.annotation-actions button:last-child').click()")
            running.wait("document.getElementById('annotation-count').textContent==='0'", 'packaged app deletes a mark')
            running.close()
            running = PackagedApp(executable, folder)
            assert running.evaluate("document.getElementById('annotation-count').textContent==='0' && !document.querySelector('.annotation-badge')")
            assert source.read_text() == original
            running.close()
            print('PASS: annotation deletions persist and the source file stays unchanged', flush=True)
            if os.environ.get('DISPLAY'):
                running = PackagedApp(executable, folder, platform='xcb')
                listing = subprocess.check_output(['xprop', '-root', '_NET_CLIENT_LIST'], text=True)
                matched = False
                for window in re.findall(r'0x[0-9a-fA-F]+', listing):
                    properties = subprocess.check_output(['xprop', '-id', window, '_NET_WM_PID', 'WM_CLASS', '_NET_WM_ICON'], text=True)
                    if re.search(r'_NET_WM_PID\(CARDINAL\) = ' + str(running.process.pid) + r'\b', properties):
                        assert '"Khana"' in properties
                        assert '_NET_WM_ICON(CARDINAL)' in properties
                        matched = True
                assert matched, 'X11 application window was not found'
                running.close()
                print('PASS: actual X11 class and window icon match the installed app', flush=True)
            print(f'Debian package smoke test passed: {package}', flush=True)
        finally:
            if running:
                running.stop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
