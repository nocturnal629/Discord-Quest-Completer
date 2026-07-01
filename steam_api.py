import os
import requests


def search_steam_game(query):
    resp = requests.get(
        'https://store.steampowered.com/api/storesearch/',
        params={'term': query, 'l': 'english', 'cc': 'US'},
        timeout=15,
    )
    resp.raise_for_status()
    items = resp.json().get('items')
    if not items:
        return None

    app_id   = items[0]['id']
    official = items[0]['name']

    resp2 = requests.get(
        f'https://api.steamcmd.net/v1/info/{app_id}',
        timeout=15,
    )
    resp2.raise_for_status()
    app_data = resp2.json().get('data', {}).get(str(app_id), {})
    config   = app_data.get('config', {})

    install_dir  = config.get('installdir', official)
    exe_rel_path = _pick_windows_exe(config.get('launch', {}))
    relative_path = os.path.join(install_dir, exe_rel_path) if exe_rel_path else install_dir

    return {
        'official_name': official,
        'app_id': app_id,
        'relative_path': relative_path,
    }


def _pick_windows_exe(launch_data):
    if not launch_data:
        return ''
    candidates = []
    for entry in launch_data.values():
        oslist = entry.get('config', {}).get('oslist', '')
        if not oslist or 'windows' in oslist.lower():
            exe = entry.get('executable', '')
            if exe and exe.lower().endswith('.exe'):
                candidates.append((entry.get('type', ''), exe))
    if not candidates:
        return ''
    for launch_type, exe in candidates:
        if launch_type == 'default':
            return exe
    return candidates[0][1]
