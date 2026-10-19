"""Render the actual chezmoi templates for every supported machine."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHEZMOI = os.environ.get('CHEZMOI_BIN') or shutil.which('chezmoi')


@unittest.skipUnless(CHEZMOI, 'chezmoi is required for profile rendering')
class Profiles(unittest.TestCase):
    def render(self, host, template):
        return subprocess.run(
            [CHEZMOI, '--source', str(ROOT), '--override-data',
             json.dumps({'chezmoi': {'hostname': host}}), 'execute-template'],
            input=template, text=True, capture_output=True, check=True).stdout

    def test_profiles_render_without_conflicting_bindings(self):
        for host in ['molly', 'funkypunk', 'badapple']:
            with self.subTest(host=host):
                text = self.render(host, (ROOT/'dot_config/sway/config.tmpl').read_text())
                self.assertEqual('exec awcc' in text, host == 'funkypunk')
                self.assertEqual('input "type:touchpad"' in text, host != 'molly')
                self.assertEqual('output DP-1 {' in text, host == 'molly')
                self.assertEqual('bindsym $mod+q kill' in text, host == 'molly')
                self.assertEqual('bindsym $mod+Ctrl+Up exec' in text, host == 'molly')
                self.assertEqual('bindsym $mod+a exec' in text, host == 'molly')
                self.assertEqual('bindsym Print exec' in text, host != 'molly')
                self.assertEqual('bindsym XF86MonBrightnessUp exec' in text, host != 'molly')
                self.assertNotIn('bindsym $mod+Mod1+Up exec brightnessctl', text)
                self.assertIn('XF86AudioRaiseVolume exec', text)
                self.assertIn('XF86AudioPlay exec', text)
                variables, seen, mode = {}, {}, 'default'
                for line in text.splitlines():
                    if line.startswith('set '):
                        parts = line.split(maxsplit=2)
                        if len(parts) == 3:
                            variables[parts[1]] = parts[2]
                    if line.startswith('mode '):
                        mode = line.split('"')[1]
                    if line == '}':
                        mode = 'default'
                    parts = line.strip().split()
                    if not parts or parts[0] != 'bindsym':
                        continue
                    key = next(p for p in parts[1:] if not p.startswith('--'))
                    for name, value in variables.items():
                        key = key.replace(name, value)
                    key = key.replace('Ctrl', 'Control').replace('Alt', 'Mod1')
                    combination = (mode, tuple(sorted(key.split('+'))))
                    self.assertNotIn(combination, seen, (host, line, seen.get(combination)))
                    seen[combination] = line

    def test_waybar_retains_laptop_battery_and_drawers(self):
        for host in ['molly', 'funkypunk', 'badapple']:
            with self.subTest(host=host):
                text = self.render(host, (ROOT/'dot_config/waybar/config.jsonc.tmpl').read_text())
                data = json.loads(re.sub(r'^\s*//.*$', '', text, flags=re.M))
                self.assertEqual('battery' in data['modules-right'], host != 'molly')
                self.assertIn('drawer', data['group/network'])
                self.assertEqual(data['sway/workspaces']['format-icons']['1'], '一')

    def test_machine_specific_aur_manifest(self):
        template = ('{{ range .packages.aur.common }}{{ . }}{{ "\\n" }}{{ end }}'
                    '{{ with index .packages.aur .chezmoi.hostname }}'
                    '{{ range . }}{{ . }}{{ "\\n" }}{{ end }}{{ end }}')
        for host in ['molly', 'funkypunk', 'badapple']:
            with self.subTest(host=host):
                packages = self.render(host, template).splitlines()
                self.assertEqual('awcc-bin' in packages, host == 'funkypunk')


if __name__ == '__main__':
    unittest.main()
