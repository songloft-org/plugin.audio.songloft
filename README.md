# plugin.audio.songloft

Kodi 插件，用于播放 [Songloft](https://github.com/altman08/songloft-player) 自托管音乐服务器上的音乐。

## 功能

- 歌曲库浏览与分页
- 歌单列表与歌单内歌曲浏览
- 歌曲搜索
- 本地文件流式播放（通过后端代理）
- 网络/远程歌曲直接播放
- JWT 登录鉴权（access_token 自动携带）
- **多服务器支持**：最多配置 5 个服务器，主菜单一键切换

## 已知限制

- **不支持 Songloft JS 插件**：Songloft 的 JS 插件系统（jsplugin）本质上是运行在 WebView/浏览器中的前端网页应用，Kodi 没有内置浏览器，也无法在插件环境中执行 JavaScript，因此无法渲染或交互。此 Kodi 插件仅对接 Songloft 后端的原生 REST API（歌曲库、歌单、搜索、播放），不支持通过 JS 插件扩展的内容来源。

## 安装

### 方式一：从 Release 下载（推荐）

1. 前往 [Releases](../../releases) 页面，下载最新的 `plugin.audio.songloft-*.zip`
2. Kodi → 设置 → 插件 → 从 zip 文件安装
3. 选择下载的 zip 文件完成安装

### 方式二：手动打包

```bash
cd ..
zip -r plugin.audio.songloft.zip plugin.audio.songloft/ \
  --exclude "plugin.audio.songloft/.git/*" \
  --exclude "plugin.audio.songloft/*.zip" \
  --exclude "plugin.audio.songloft/screenshot/*" \
  --exclude "plugin.audio.songloft/README.md"
```

## 配置

安装后在插件设置中配置服务器（支持最多 5 个）：

| 设置项 | 说明 | 默认值 |
|--------|------|--------|
| 名称 | 服务器显示名称，如"家里"、"公司" | — |
| 服务器地址 | Songloft 服务端地址，如 `http://192.168.1.100:58091` | `http://localhost:58091`（服务器 1） |
| 用户名 | 登录用户名 | — |
| 密码 | 登录密码 | — |
| 每页歌曲数 | 分页大小：20 / 50 / 100 / 200 | 50 |

### 切换服务器

主菜单底部显示当前激活的服务器名称，点击后弹出服务器选择列表，可查看各服务器登录状态并一键切换。切换时若目标服务器尚未登录会自动触发登录。

## 依赖

- [script.module.xbmcswift2](https://kodi.wiki/view/Add-on:Module:xbmcswift2) ≥ 2.4.0
- [script.module.requests](https://kodi.wiki/view/Add-on:Module:Requests) ≥ 2.19.1

## 发布新版本

1. 更新 `addon.xml` 中的 `version` 属性和 `<news>` 内容
2. 推送 tag：

```bash
git tag v1.0.1
git push origin v1.0.1
```

GitHub Actions 会自动打包并创建 Release。

## 截图

![截图1](screenshot/1.png)
![截图2](screenshot/2.png)
![截图3](screenshot/3.png)
