# -*- coding: utf-8 -*-
"""
Songloft Kodi 插件
通过 Kodi 播放 Songloft 自托管音乐服务器上的音乐
支持多服务器配置，可在主菜单切换当前活跃服务器
"""

import sys
from xbmcswift2 import Plugin, xbmcgui, xbmcplugin, xbmc
from api import SongloftApi, SongloftException

plugin = Plugin()

# ------------------------------------------------------------------ #
# 存储
# ------------------------------------------------------------------ #
# _storage 结构：
#   active_server: int (0-4, 对应服务器 1-5 的索引)
#   servers: list of {
#       access_token: str,
#       refresh_token: str,
#       logged_in: bool,
#   }
# ------------------------------------------------------------------ #

_storage = plugin.get_storage('account')

# 初始化存储默认值
if 'active_server' not in _storage:
    _storage['active_server'] = 0
if 'servers' not in _storage:
    _storage['servers'] = [{
        'access_token': '',
        'refresh_token': '',
        'logged_in': False,
    } for _ in range(5)]


# ------------------------------------------------------------------ #
# 辅助：设置读取
# ------------------------------------------------------------------ #

def _get_setting(key):
    return xbmcplugin.getSetting(int(sys.argv[1]), key)


def _get_page_size():
    return 50


def _get_server_config(idx):
    """从 settings 读取第 idx 个服务器配置（idx 从 0 开始）"""
    n = idx + 1  # settings.xml 用 server1_* ~ server5_*
    return {
        'name':     _get_setting('server{}_name'.format(n)).strip(),
        'url':      _get_setting('server{}_url'.format(n)).strip().rstrip('/'),
        'username': _get_setting('server{}_username'.format(n)).strip(),
        'password': _get_setting('server{}_password'.format(n)).strip(),
    }


def _get_configured_servers():
    """返回所有已填写服务器地址的服务器列表，每项带 idx 字段"""
    result = []
    for i in range(5):
        cfg = _get_server_config(i)
        if cfg['url']:
            cfg['idx'] = i
            result.append(cfg)
    return result


# ------------------------------------------------------------------ #
# 辅助：活跃服务器
# ------------------------------------------------------------------ #

def _active_idx():
    return int(_storage.get('active_server', 0))


def _get_server_storage(idx=None):
    """获取指定服务器的 token 存储 dict（可写）"""
    if idx is None:
        idx = _active_idx()
    servers = _storage.get('servers', [])
    # 补足到5个
    while len(servers) < 5:
        servers.append({'access_token': '', 'refresh_token': '', 'logged_in': False})
    return servers[idx]


def _save_servers():
    """触发 storage 持久化（xbmcswift2 的 dict storage 赋值时自动保存，这里强制写回）"""
    _storage['servers'] = _storage['servers']


def _get_active_token():
    return _get_server_storage().get('access_token', '')


def _get_base_url(idx=None):
    if idx is None:
        idx = _active_idx()
    url = _get_server_config(idx)['url']
    if not url:
        url = 'http://localhost:58091'
    return url


def _make_api(idx=None):
    if idx is None:
        idx = _active_idx()
    token = _get_server_storage(idx).get('access_token', '')
    return SongloftApi(_get_base_url(idx), access_token=token)


# ------------------------------------------------------------------ #
# 辅助：通知
# ------------------------------------------------------------------ #

def _notify(title, message, icon=xbmcgui.NOTIFICATION_INFO, time=2500):
    xbmcgui.Dialog().notification(title, message, icon, time, False)


def _notify_error(title, message):
    xbmcgui.Dialog().notification(title, message, xbmcgui.NOTIFICATION_ERROR, 3000, False)


# ------------------------------------------------------------------ #
# 辅助：登录
# ------------------------------------------------------------------ #

def _ensure_logged_in():
    """检查当前活跃服务器是否已登录，若没有则自动尝试登录"""
    srv = _get_server_storage()
    if srv.get('logged_in') and srv.get('access_token'):
        return True
    return _do_login(_active_idx())


def _do_login(idx):
    """对指定服务器执行登录，成功返回 True"""
    cfg = _get_server_config(idx)
    base_url = cfg['url']
    username = cfg['username']
    password = cfg['password']

    if not base_url:
        _notify_error('登录失败', '服务器 {} 未配置地址，请检查设置'.format(idx + 1))
        return False
    if not username or not password:
        _notify_error('登录失败', '服务器 {} 未配置用户名/密码，请检查设置'.format(idx + 1))
        return False

    api = SongloftApi(base_url)
    try:
        tokens = api.login(username, password)
        srv = _get_server_storage(idx)
        srv['access_token'] = tokens.get('access_token', '')
        srv['refresh_token'] = tokens.get('refresh_token', '')
        srv['logged_in'] = True
        _save_servers()
        name = cfg['name'] or '服务器 {}'.format(idx + 1)
        _notify('登录成功', '已连接到 {}'.format(name))
        return True
    except SongloftException as e:
        srv = _get_server_storage(idx)
        srv['logged_in'] = False
        srv['access_token'] = ''
        _save_servers()
        _notify_error('登录失败', e.message)
        return False


# ------------------------------------------------------------------ #
# 辅助：URL 构建
# ------------------------------------------------------------------ #

def _build_url_with_token(url, base_url, token):
    """构建带 access_token 查询参数的完整 URL。
    后端通过 ?access_token=<token> 鉴权（不支持 Authorization Header）。
    """
    if not url:
        return ''
    if url.startswith('/'):
        url = base_url + url
    if token:
        sep = '&' if '?' in url else '?'
        url = '{}{}access_token={}'.format(url, sep, token)
    return url


def _fetch_all_songs(api, base_url, token, playlist_id=None, batch=200):
    """分批拉取全部歌曲，返回 xbmcgui.ListItem 列表（已附带元数据和封面）。
    playlist_id 不为 None 时拉取歌单内歌曲，否则拉取歌曲库。
    """
    all_items = []
    offset = 0
    while True:
        try:
            if playlist_id is not None:
                resp = api.get_playlist_songs(playlist_id, limit=batch, offset=offset)
            else:
                resp = api.get_songs(limit=batch, offset=offset)
        except SongloftException:
            break
        songs = resp.get('songs', [])
        total = resp.get('total', 0)
        for song in songs:
            title = song.get('title') or '未知歌曲'
            artist = song.get('artist') or ''
            album = song.get('album') or ''
            duration_raw = song.get('duration', 0)
            try:
                duration_secs = int(float(duration_raw))
            except (TypeError, ValueError):
                duration_secs = 0
            cover_url = _build_url_with_token(song.get('cover_url') or '', base_url, token)
            play_url = _build_url_with_token(song.get('url') or '', base_url, token)
            if not play_url:
                continue
            li = xbmcgui.ListItem(label=title, path=play_url)
            li.setArt({'thumb': cover_url, 'icon': cover_url}) if cover_url else None
            try:
                tag = li.getMusicInfoTag()
                tag.setTitle(title)
                if artist:
                    tag.setArtist(artist)
                if album:
                    tag.setAlbum(album)
                if duration_secs:
                    tag.setDuration(duration_secs)
            except AttributeError:
                li.setInfo('music', {
                    'title': title, 'artist': artist,
                    'album': album, 'duration': duration_secs,
                })
            all_items.append((play_url, li))
        offset += len(songs)
        if offset >= total or not songs:
            break
    return all_items


def _song_to_item(song, base_url, token=''):
    """将 Songloft 歌曲 dict 转换为 xbmcswift2 item dict"""
    title = song.get('title') or '未知歌曲'
    artist = song.get('artist') or ''
    album = song.get('album') or ''
    duration_raw = song.get('duration', 0)
    try:
        duration_secs = int(float(duration_raw))
    except (TypeError, ValueError):
        duration_secs = 0

    if artist:
        label = '{} - {}'.format(artist, title)
    else:
        label = title

    song_id = song.get('id')
    cover_url = song.get('cover_url') or ''
    cover_url = _build_url_with_token(cover_url, base_url, token)

    item_path = plugin.url_for('play_song', song_id=str(song_id))

    return {
        'label': label,
        'path': item_path,
        'is_playable': True,
        'icon': cover_url or None,
        'thumbnail': cover_url or None,
        'info': {
            'title': title,
            'artist': artist,
            'album': album,
            'duration': duration_secs,
        },
        'info_type': 'music',
        'properties': {
            '_songloft_id': str(song_id),
        },
    }


# ================================================================== #
# 路由
# ================================================================== #

@plugin.route('/')
def index():
    """主菜单"""
    if not _ensure_logged_in():
        return []

    idx = _active_idx()
    cfg = _get_server_config(idx)
    server_name = cfg['name'] or cfg['url'] or '服务器 {}'.format(idx + 1)

    items = [
        {
            'label': '歌曲库',
            'path': plugin.url_for('library', offset='0'),
        },
        {
            'label': '我的歌单',
            'path': plugin.url_for('playlists', offset='0'),
        },
        {
            'label': '搜索',
            'path': plugin.url_for('search'),
        },
        {
            'label': '当前服务器：[COLOR gray]{}[/COLOR]'.format(server_name),
            'path': plugin.url_for('switch_server'),
        },
    ]
    return items


# ------------------------------------------------------------------ #
# 切换服务器
# ------------------------------------------------------------------ #

@plugin.route('/switch_server/')
def switch_server():
    """弹出服务器选择对话框，切换活跃服务器"""
    servers = _get_configured_servers()
    if not servers:
        _notify_error('切换服务器', '未配置任何服务器，请先在插件设置中添加服务器')
        return

    active_idx = _active_idx()
    labels = []
    for s in servers:
        name = s['name'] or s['url']
        srv_storage = _get_server_storage(s['idx'])
        logged = srv_storage.get('logged_in', False)
        status = '[COLOR green]已登录[/COLOR]' if logged else '[COLOR gray]未登录[/COLOR]'
        # 标记当前活跃
        if s['idx'] == active_idx:
            prefix = '[COLOR yellow]* [/COLOR]'
        else:
            prefix = ''
        labels.append('{}{} - {}'.format(prefix, name, status))

    dialog = xbmcgui.Dialog()
    sel = dialog.select('选择服务器', labels)
    if sel < 0:
        return

    chosen = servers[sel]
    _storage['active_server'] = chosen['idx']

    # 如果该服务器尚未登录，立即触发登录
    srv_storage = _get_server_storage(chosen['idx'])
    if not srv_storage.get('logged_in') or not srv_storage.get('access_token'):
        _do_login(chosen['idx'])

    xbmc.executebuiltin('Container.Refresh')


# ------------------------------------------------------------------ #
# 重新登录（对当前活跃服务器）
# ------------------------------------------------------------------ #

@plugin.route('/relogin/')
def relogin():
    """强制重新登录当前活跃服务器"""
    idx = _active_idx()
    srv = _get_server_storage(idx)
    srv['logged_in'] = False
    srv['access_token'] = ''
    _save_servers()
    if _do_login(idx):
        xbmc.executebuiltin('Container.Refresh')


# ------------------------------------------------------------------ #
# 歌曲库
# ------------------------------------------------------------------ #

@plugin.route('/library/<offset>/')
def library(offset):
    """歌曲库（分页）"""
    if not _ensure_logged_in():
        return []

    api = _make_api()
    page_size = _get_page_size()
    offset = int(offset)
    base_url = _get_base_url()
    token = _get_active_token()

    try:
        resp = api.get_songs(limit=page_size, offset=offset)
    except SongloftException as e:
        _notify_error('加载失败', e.message)
        return []

    songs = resp.get('songs', [])
    total = resp.get('total', 0)
    items = [_song_to_item(s, base_url, token) for s in songs]

    # 顶部加入"播放全部"入口（仅第一页显示，避免重复）
    if offset == 0 and total > 0:
        items.insert(0, {
            'label': '[COLOR green]▶ 播放全部 ({} 首)[/COLOR]'.format(total),
            'path': plugin.url_for('play_all_library'),
        })

    if offset + len(songs) < total:
        items.append({
            'label': '[COLOR yellow]下一页 ({}/{})…[/COLOR]'.format(offset + len(songs), total),
            'path': plugin.url_for('library', offset=str(offset + page_size)),
        })

    return items


# ------------------------------------------------------------------ #
# 歌单列表
# ------------------------------------------------------------------ #

@plugin.route('/playlists/<offset>/')
def playlists(offset):
    """歌单列表（分页）"""
    if not _ensure_logged_in():
        return []

    api = _make_api()
    page_size = 50
    offset = int(offset)
    base_url = _get_base_url()
    token = _get_active_token()

    try:
        resp = api.get_playlists(limit=page_size, offset=offset)
    except SongloftException as e:
        _notify_error('加载失败', e.message)
        return []

    pl_list = resp.get('playlists', [])
    total = resp.get('total', 0)
    items = []

    for pl in pl_list:
        pl_id = pl.get('id')
        name = pl.get('name') or '未命名歌单'
        description = pl.get('description') or ''
        song_count = pl.get('song_count', 0)
        cover = pl.get('cover_url') or ''
        cover = _build_url_with_token(cover, base_url, token)

        pl_type = pl.get('type', 'normal')
        type_label = {'normal': '歌单', 'radio': '电台', 'album': '专辑'}.get(pl_type, '歌单')

        plot = '[COLOR pink]{}[/COLOR]  {}首歌\n'.format(name, song_count)
        if description:
            plot += description + '\n'
        plot += '类型: {}\n'.format(type_label)

        items.append({
            'label': name,
            'path': plugin.url_for('playlist_songs', playlist_id=str(pl_id), offset='0'),
            'icon': cover or None,
            'thumbnail': cover or None,
            'info': {
                'plot': plot,
            },
        })

    if offset + len(pl_list) < total:
        items.append({
            'label': '[COLOR yellow]下一页…[/COLOR]',
            'path': plugin.url_for('playlists', offset=str(offset + page_size)),
        })

    return items


# ------------------------------------------------------------------ #
# 歌单内歌曲
# ------------------------------------------------------------------ #

@plugin.route('/playlist/<playlist_id>/<offset>/')
def playlist_songs(playlist_id, offset):
    """歌单内歌曲（分页）"""
    if not _ensure_logged_in():
        return []

    api = _make_api()
    page_size = _get_page_size()
    offset = int(offset)
    base_url = _get_base_url()
    token = _get_active_token()

    try:
        resp = api.get_playlist_songs(playlist_id, limit=page_size, offset=offset)
    except SongloftException as e:
        _notify_error('加载失败', e.message)
        return []

    songs = resp.get('songs', [])
    total = resp.get('total', 0)
    items = [_song_to_item(s, base_url, token) for s in songs]

    # 顶部加入"播放全部"入口（仅第一页显示，避免重复）
    if offset == 0 and total > 0:
        items.insert(0, {
            'label': '[COLOR green]▶ 播放全部 ({} 首)[/COLOR]'.format(total),
            'path': plugin.url_for('play_all_playlist', playlist_id=str(playlist_id)),
        })

    if offset + len(songs) < total:
        items.append({
            'label': '[COLOR yellow]下一页 ({}/{})…[/COLOR]'.format(offset + len(songs), total),
            'path': plugin.url_for('playlist_songs', playlist_id=str(playlist_id), offset=str(offset + page_size)),
        })

    return items


# ------------------------------------------------------------------ #
# 搜索
# ------------------------------------------------------------------ #

@plugin.route('/search/')
def search():
    """搜索歌曲"""
    if not _ensure_logged_in():
        return []

    keyboard = xbmc.Keyboard('', '搜索歌曲（标题/艺术家/专辑）')
    keyboard.doModal()
    if not keyboard.isConfirmed():
        return []

    keyword = keyboard.getText().strip()
    if not keyword:
        return []

    api = _make_api()
    base_url = _get_base_url()
    page_size = _get_page_size()
    token = _get_active_token()

    try:
        resp = api.get_songs(limit=page_size, offset=0, keyword=keyword)
    except SongloftException as e:
        _notify_error('搜索失败', e.message)
        return []

    songs = resp.get('songs', [])
    total = resp.get('total', 0)

    if not songs:
        _notify('搜索', '未找到匹配的歌曲')
        return []

    items = [_song_to_item(s, base_url, token) for s in songs]

    if total > page_size:
        items.append({
            'label': '[COLOR gray]共 {} 首，仅显示前 {} 首[/COLOR]'.format(total, page_size),
            'path': plugin.url_for('search_results', keyword=keyword, offset=str(page_size)),
        })

    return items


@plugin.route('/search_results/<keyword>/<offset>/')
def search_results(keyword, offset):
    """搜索结果分页"""
    if not _ensure_logged_in():
        return []

    api = _make_api()
    base_url = _get_base_url()
    page_size = _get_page_size()
    offset = int(offset)
    token = _get_active_token()

    try:
        resp = api.get_songs(limit=page_size, offset=offset, keyword=keyword)
    except SongloftException as e:
        _notify_error('搜索失败', e.message)
        return []

    songs = resp.get('songs', [])
    total = resp.get('total', 0)
    items = [_song_to_item(s, base_url, token) for s in songs]

    if offset + len(songs) < total:
        items.append({
            'label': '[COLOR yellow]下一页 ({}/{})…[/COLOR]'.format(offset + len(songs), total),
            'path': plugin.url_for('search_results', keyword=keyword, offset=str(offset + page_size)),
        })

    return items


# ------------------------------------------------------------------ #
# 播放全部（跨分页）
# ------------------------------------------------------------------ #

def _play_all(api, base_url, token, playlist_id=None, label='歌曲库'):
    """拉取全部歌曲并加入 Kodi 音乐播放列表后开始播放"""
    _notify('加载中', '正在加载全部歌曲，请稍候…')
    items = _fetch_all_songs(api, base_url, token, playlist_id=playlist_id)
    if not items:
        _notify_error('播放全部', '未能加载到任何歌曲')
        return

    playlist = xbmc.PlayList(xbmc.PLAYLIST_MUSIC)
    playlist.clear()
    for play_url, li in items:
        playlist.add(play_url, li)

    xbmc.Player().play(playlist)
    _notify('播放全部', '{} 首歌曲已加入播放列表'.format(len(items)))


@plugin.route('/play_all/library/')
def play_all_library():
    """播放整个歌曲库（跨分页拉取全部）"""
    if not _ensure_logged_in():
        return
    api = _make_api()
    base_url = _get_base_url()
    token = _get_active_token()
    _play_all(api, base_url, token, playlist_id=None, label='歌曲库')


@plugin.route('/play_all/playlist/<playlist_id>/')
def play_all_playlist(playlist_id):
    """播放整个歌单（跨分页拉取全部）"""
    if not _ensure_logged_in():
        return
    api = _make_api()
    base_url = _get_base_url()
    token = _get_active_token()
    _play_all(api, base_url, token, playlist_id=playlist_id, label='歌单')


# ------------------------------------------------------------------ #
# 播放
# ------------------------------------------------------------------ #

@plugin.route('/play/<song_id>/')
def play_song(song_id):
    """解析并播放歌曲"""
    if not _ensure_logged_in():
        plugin.set_resolved_url(None)
        return

    api = _make_api()
    base_url = _get_base_url()
    token = _get_active_token()

    try:
        song = api.get_song(int(song_id))
    except SongloftException as e:
        _notify_error('播放失败', e.message)
        plugin.set_resolved_url(None)
        return

    # song.url 是后端返回的相对路径（如 /api/v1/songs/152/audio）
    # 后端通过 ?access_token= 查询参数鉴权
    play_url = song.get('url') or ''

    if not play_url:
        _notify_error('播放失败', '无法获取歌曲播放地址')
        plugin.set_resolved_url(None)
        return

    # 通知后端播放开始事件（失败不影响播放）
    try:
        api.notify_played(int(song_id), play_type='play')
    except Exception:
        pass

    play_url = _build_url_with_token(play_url, base_url, token)

    # 构建带封面的 ListItem，确保播放时 Kodi 能显示专辑封面
    title = song.get('title') or ''
    artist = song.get('artist') or ''
    album = song.get('album') or ''
    cover_url = song.get('cover_url') or ''
    cover_url = _build_url_with_token(cover_url, base_url, token)
    duration_raw = song.get('duration', 0)
    try:
        duration_secs = int(float(duration_raw))
    except (TypeError, ValueError):
        duration_secs = 0

    # 通过 xbmcswift2 框架的 set_resolved_url 保证框架状态正确
    # 框架会正确设置 _end_of_directory 标志，避免 handle 被二次调用导致播放失败
    play_item = {
        'label': title,
        'path': play_url,
        'info_type': 'music',
        'info': {
            'title': title,
            'artist': artist,
            'album': album,
            'duration': duration_secs,
        },
    }
    if cover_url:
        # thumbnail/icon 供旧版 Kodi 使用
        play_item['thumbnail'] = cover_url
        play_item['icon'] = cover_url

    resolved = plugin.set_resolved_url(play_item)

    # 新版 Kodi (v19+) 已废弃 setThumbnailImage，需额外调用 setArt 设置封面
    if cover_url and resolved:
        try:
            resolved[0].as_xbmc_listitem().setArt({
                'thumb': cover_url,
                'icon': cover_url,
                'fanart': cover_url,
            })
        except Exception:
            pass


if __name__ == '__main__':
    plugin.run()
