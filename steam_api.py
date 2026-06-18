from steam.client import SteamClient
import requests, os

COMMON_FOLDER = r'C:\Program Files (x86)\Steam\steamapps\common'


def get_game_path_by_name(game_query):
    search_url = (
        f'https://store.steampowered.com/api/storesearch/'
        f'?term={game_query}&l=english&cc=US'
    )
    search_resp = requests.get(search_url, timeout=15).json()

    if not search_resp.get('items'):
        return None

    game_data = search_resp['items'][0]
    app_id = game_data['id']
    official_name = game_data['name']

    client = SteamClient()
    try:
        client.anonymous_login()
        product_info = client.get_product_info(apps=[app_id])

        if not product_info or 'apps' not in product_info:
            return None

        app_config = product_info['apps'][app_id].get('config', {})
        install_dir = app_config.get('installdir', official_name)
        launch_data = app_config.get('launch', {})
        exe_rel_path = 'unknown.exe'

        if launch_data:
            first_launch = list(launch_data.values())[0]
            exe_rel_path = first_launch.get('executable', '')

        full_path = os.path.join(COMMON_FOLDER, install_dir, exe_rel_path)
        return {
            'official_name': official_name,
            'app_id': app_id,
            'install_dir': install_dir,
            'exe_rel_path': exe_rel_path,
            'full_path': full_path,
        }
    finally:
        client.disconnect()
