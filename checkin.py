"""
Cloak Browser 自动签到助手 | Cloak Browser Check-in Assistant
https://cloakbrowser.dev

所有站点配置从 config.json 读取，首次运行请执行 run.sh / run.bat。
"""

import json
import sys
import time
from pathlib import Path
import os
import urllib.parse

from cloakbrowser import launch_persistent_context

BASE_DIR = Path(__file__).parent

# ── 内置站点模板（可在 config.json 中覆盖或新增任意 NexusPHP 站点） ─────────
TEMPLATES: dict[str, dict] = {
    "ourbits": {
        "url": "https://ourbits.club",
        "login_path": "/login.php",
        "checkin_path": "/attendance.php",
        "checkin_type": "turnstile",
        "login_captcha": False,
        "login_fields": {"username": "username", "password": "password"},
    },
    "hdkyl": {
        "url": "https://www.hdkyl.in",
        "login_path": "/login.php",
        "checkin_path": "/attendance.php",
        "checkin_type": "turnstile",
        "login_captcha": False,
        "login_fields": {"username": "username", "password": "password"},
    },
    "hitpt": {
        "url": "https://www.hitpt.com",
        "login_path": "/login.php",
        "checkin_path": "/attendance.php",
        "checkin_type": "turnstile",
        "login_captcha": False,
        "login_fields": {"username": "username", "password": "password"},
    },
    "piggo": {
        "url": "https://piggo.me",
        "login_path": "/login.php",
        "checkin_path": "/attendance.php",
        "checkin_type": "turnstile",
        "login_captcha": False,
        "login_fields": {"username": "username", "password": "password"},
    },
    "audiences": {
        "url": "https://audiences.me",
        "login_path": "/login.php",
        "checkin_path": "/attendance.php",
        "checkin_type": "turnstile",
        "login_captcha": True,
        "login_fields": {
            "username": "username",
            "password": "password",
            "captcha_code": "imagestring",
            "captcha_hash": "imagehash",
        },
        "captcha_image_selector": 'img[alt="CAPTCHA"]',
    },
}


# ── 配置加载 ──────────────────────────────────────────────────────────────────

def load_config() -> dict:
    cfg_path = BASE_DIR / "config.json"
    if not cfg_path.exists():
        print("[!] 未找到 config.json。请先运行 run.sh 或 run.bat 进行配置。")
        print("    config.json not found. Run run.sh or run.bat first.")
        sys.exit(1)
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[!] config.json 格式错误: {e}")
        sys.exit(1)


def build_sites(config: dict) -> list[dict]:
    """将 config.json 中的站点列表与内置模板合并，返回完整站点配置。"""
    sites = []
    for entry in config.get("sites", []):
        if not entry.get("enabled", True):
            continue
        name = entry.get("name", "")
        if not name:
            continue
        # 以内置模板为基础，config.json 中的字段可覆盖
        site = dict(TEMPLATES.get(name, {}))
        site.update(entry)
        if not site.get("url"):
            print(f"[!] 站点 '{name}' 缺少 url，已跳过。")
            continue
        if not site.get("username") or not site.get("password"):
            print(f"[!] 站点 '{name}' 缺少账号或密码，已跳过。")
            continue
        sites.append(site)
    return sites


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def get_profile_dir(site_name: str) -> str:
    return str(BASE_DIR / f"profile_{site_name}")


def get_cookies_file(site_name: str) -> Path:
    return BASE_DIR / f"cookies_{site_name}.json"


def save_cookies(context, site_name: str):
    cookies = context.cookies()
    get_cookies_file(site_name).write_text(json.dumps(cookies, indent=2))


def load_cookies(context, site_name: str) -> bool:
    f = get_cookies_file(site_name)
    if not f.exists():
        return False
    try:
        cookies = json.loads(f.read_text())
        context.add_cookies(cookies)
        return True
    except (json.JSONDecodeError, KeyError):
        return False


def wait_past_cf(page, timeout=300) -> bool:
    """等待 Cloudflare 验证完成。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            title = page.title()
            body = page.evaluate("() => document.body ? document.body.innerText.substring(0, 300) : ''")
            if "安全验证" not in body and "Just a moment" not in title:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


# ── Bark 通知 ──────────────────────────────────────────────────────────────────

def send_bark_notification(title: str, body: str, is_critical: bool = False) -> bool:
    """
    发送 Bark 通知到 iOS 设备
    
    Args:
        title: 通知标题
        body: 通知正文
        is_critical: 是否为紧急通知（失败时设为 True，会带上 critical 参数）
    """
    import requests
    
    bark_key = os.getenv("BARK_KEY")
    bark_url = os.getenv("BARK_URL", "https://api.day.app")
    
    if not bark_key:
        print("    [!] 未配置 BARK_KEY 环境变量，跳过通知")
        return False
    
    try:
        # Bark API 格式: https://api.day.app/{key}/{title}/{body}
        encoded_title = urllib.parse.quote(title, safe='')
        encoded_body = urllib.parse.quote(body, safe='')
        
        # 构建基础 URL
        base_url = f"{bark_url}/{bark_key}/{encoded_title}/{encoded_body}"
        
        # 构建查询参数
        params = {
            "sound": "minuet",
            "icon": "https://github.com/fluidicon.png",
            "group": "PT签到"
        }
        
        # 如果是紧急通知，添加 critical 和 volume 参数
        if is_critical:
            params["level"] = "critical"
            params["volume"] = "0"  # 静音紧急通知（只震动不响铃）
            print("    [*] 发送紧急通知（签到失败）")
        else:
            params["level"] = "active"
        
        # 发送请求
        response = requests.get(base_url, params=params, timeout=10)
        
        if response.status_code == 200:
            print("    [+] Bark 通知发送成功")
            return True
        else:
            print(f"    [!] Bark 通知发送失败: HTTP {response.status_code}")
            print(f"        响应内容: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"    [!] Bark 通知异常: {e}")
        return False


# ── 验证码处理 ────────────────────────────────────────────────────────────────

def handle_captcha(page, site_config: dict) -> bool:
    if not site_config.get("login_captcha"):
        return True

    captcha_field = site_config["login_fields"].get("captcha_code", "imagestring")
    has_captcha = page.evaluate(f"() => document.querySelector('input[name=\"{captcha_field}\"]') !== null")
    if not has_captcha:
        return True

    img_selector = site_config.get("captcha_image_selector", 'img[alt="CAPTCHA"]')
    img_src = page.evaluate(f"""() => {{
        const img = document.querySelector('{img_selector}');
        return img ? img.src : null;
    }}""")

    if not img_src:
        print("    [!] 未找到验证码图片")
        return False

    print(f"    [*] 需要验证码，图片地址：{img_src[:120]}")

    cap_path = BASE_DIR / f"captcha_{site_config['name']}.png"
    try:
        import urllib.request
        cookies = page.context.cookies()
        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        req = urllib.request.Request(img_src.replace("&amp;", "&"), headers={
            "Cookie": cookie_header,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            cap_path.write_bytes(resp.read())
        print(f"    [*] 验证码已保存至：{cap_path}")
    except Exception as e:
        print(f"    [!] 无法下载验证码：{e}")

    code = input(f"    请输入 {site_config['name']} 的验证码：").strip()
    if not code:
        print("    [-] 未输入验证码，跳过登录")
        return False

    page.fill(f'input[name="{captcha_field}"]', code)

    hash_field = site_config["login_fields"].get("captcha_hash")
    if hash_field:
        imagehash = img_src.split("imagehash=")[-1] if "imagehash=" in img_src else ""
        if imagehash:
            page.evaluate(f"""() => {{
                const el = document.querySelector('input[name="{hash_field}"]');
                if (el) el.value = '{imagehash}';
            }}""")

    return True


# ── 登录 ──────────────────────────────────────────────────────────────────────

def login(page, site_config: dict) -> bool:
    site_url = site_config["url"]
    login_url = f"{site_url}{site_config['login_path']}"
    fields = site_config["login_fields"]

    print(f"    [*] 登录 {site_url} ...")
    page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
    time.sleep(3)

    if not wait_past_cf(page, timeout=180):
        print("    [-] Cloudflare 验证超时")
        return False

    print(f"        页面：{page.title()}")

    already = page.evaluate("""() => {
        for (const a of document.querySelectorAll('a')) {
            if (a.href && (a.href.includes('userdetails') || a.href.includes('logout')))
                return true;
        }
        return false;
    }""")
    if already:
        save_cookies(page.context, site_config["name"])
        print("    [+] Cookies 有效，已登录")
        return True

    if not handle_captcha(page, site_config):
        return False

    page.fill(f'input[name="{fields["username"]}"]', site_config["username"])
    page.fill(f'input[name="{fields["password"]}"]', site_config["password"])
    page.click('input[type="submit"]')
    page.wait_for_load_state("domcontentloaded", timeout=30000)
    time.sleep(5)

    logged_in = page.evaluate("""() => {
        for (const a of document.querySelectorAll('a')) {
            if (a.href && (a.href.includes('userdetails') || a.href.includes('logout')))
                return true;
        }
        return false;
    }""")

    if logged_in:
        save_cookies(page.context, site_config["name"])
        print("    [+] 登录成功，cookies 已保存")
        return True

    error = page.evaluate("""() => {
        const row = document.querySelector('td.embedded, td.text, .error');
        return row ? row.textContent.substring(0, 200) : '';
    }""")
    print(f"    [-] 登录失败：{error[:150]}" if error else "    [-] 登录失败")
    return False


# ── 签到 ──────────────────────────────────────────────────────────────────────

def do_checkin(page, site_config: dict) -> bool:
    site_url = site_config["url"]
    checkin_url = f"{site_url}{site_config['checkin_path']}"
    checkin_type = site_config.get("checkin_type", "turnstile")

    print(f"    [*] 访问签到页面 {checkin_url} ...")
    page.goto(checkin_url, wait_until="domcontentloaded", timeout=60000)
    time.sleep(3)

    if not wait_past_cf(page, timeout=240):
        print("    [-] Cloudflare 验证超时")
        return False

    page_text = page.evaluate("() => document.body ? document.body.innerText : ''")

    if any(k in page_text for k in ["已经签到", "已签到", "已經簽到", "已簽到", "签到成功", "簽到成功"]):
        print("    [OK] 今日已签到")
        return True

    if checkin_type == "turnstile":
        return _checkin_turnstile(page)
    elif checkin_type == "form":
        return _checkin_form(page)
    elif checkin_type == "link_click":
        return _checkin_link_click(page)

    # 通用回退：依次尝试
    return _checkin_form(page) or _checkin_link_click(page) or _checkin_turnstile(page)


def _checkin_form(page) -> bool:
    submitted = page.evaluate("""() => {
        const form = document.getElementById('attendance');
        if (form) { form.submit(); return true; }
        for (const f of document.querySelectorAll('form')) {
            if (f.action && f.action.includes('attendance')) { f.submit(); return true; }
        }
        return false;
    }""")
    if submitted:
        time.sleep(3)
        body = page.evaluate("() => document.body ? document.body.innerText : ''")
        if any(k in body for k in ["成功", "已经签到", "已签到", "已經簽到"]):
            print("    [+] 签到成功！")
            return True
    return False


def _checkin_link_click(page) -> bool:
    clicked = page.evaluate("""() => {
        for (const a of document.querySelectorAll('a')) {
            const t = a.textContent || '';
            if (t.includes('签到') || t.includes('簽到') || t.includes('魔力')) {
                a.click(); return true;
            }
        }
        return false;
    }""")
    if clicked:
        time.sleep(3)
        body = page.evaluate("() => document.body ? document.body.innerText : ''")
        if any(k in body for k in ["成功", "已经签到", "已签到", "已經簽到"]):
            print("    [+] 签到成功！")
            return True
    return False


def _checkin_turnstile(page) -> bool:
    """
    处理 Cloudflare Turnstile 验证并提交签到
    """
    # 1. 等待 Turnstile 容器加载
    try:
        print("    [*] 检测 Turnstile 验证组件...")
        page.wait_for_selector('div.cf-turnstile', timeout=15000)
        print("    [+] Turnstile 容器已加载，等待自动验证...")
    except Exception:
        print("    [*] 未显式检测到 Turnstile 容器，继续尝试")

    # 2. 等待 Turnstile 自动完成（最长等待 90 秒）
    verified = False
    for attempt in range(30):  # 30 次 * 3 秒 = 90 秒
        time.sleep(3)
        try:
            # 检测 Turnstile 是否已完成（通过检查隐藏响应字段或状态变化）
            has_response = page.evaluate("""() => {
                // 检查是否存在 Turnstile 的响应字段
                const responseInput = document.querySelector('input[name="cf-turnstile-response"]');
                if (responseInput && responseInput.value) return true;
                // 或者检查 Turnstile 状态（通过 iframe 或类变化）
                const turnstile = document.querySelector('.cf-turnstile');
                if (turnstile && turnstile.getAttribute('data-response')) return true;
                return false;
            }""")
            if has_response:
                print(f"    [+] Turnstile 验证完成 (尝试 {attempt+1}/30)")
                verified = True
                break
            print(f"    [*] 等待 Turnstile 验证... ({attempt+1}/30)")
        except Exception:
            pass

    if not verified:
        print("    [!] Turnstile 验证超时，尝试强制提交")
        # 即使未检测到验证完成，也尝试提交（有些站点在无头环境下可能自动通过）

    # 3. 等待提交按钮出现并点击
    time.sleep(2)
    try:
        print("    [*] 尝试提交签到表单...")
        submit_result = page.evaluate("""() => {
            // 优先查找提交按钮
            const submitBtn = document.querySelector('input[type="submit"][value*="签到"]');
            if (submitBtn) { 
                submitBtn.click(); 
                return 'clicked_button';
            }
            // 通过表单提交
            const attendanceForm = document.querySelector('form[action*="attendance"]');
            if (attendanceForm) {
                attendanceForm.submit();
                return 'submitted_form';
            }
            // 回退：点击签到链接
            for (const a of document.querySelectorAll('a')) {
                const text = a.textContent || '';
                if (text.includes('签到') || text.includes('簽到')) {
                    a.click();
                    return 'clicked_link';
                }
            }
            return 'no_action';
        }""")
        print(f"    [+] 提交操作: {submit_result}")
    except Exception as e:
        print(f"    [!] 提交签到失败: {e}")
        return False

    # 4. 等待并验证签到结果（最长等待 60 秒）
    time.sleep(5)
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            body = page.evaluate("() => document.body ? document.body.innerText : ''")
            # 检查成功关键词
            success_keywords = ["签到成功", "已经签到", "已签到", "已經簽到", "已簽到", "簽到成功", "今日已签到", "重复签到", "请勿重复打卡"]
            for kw in success_keywords:
                if kw in body:
                    print(f"    [+] 签到成功！(检测到关键词: {kw})")
                    return True
            # 检查失败关键词
            fail_keywords = ["验证失败", "验证错误", "请重新验证", "验证码错误", "请先完成验证"]
            for kw in fail_keywords:
                if kw in body:
                    print(f"    [-] 签到失败: {kw}")
                    return False
        except Exception:
            pass
        time.sleep(3)

    print("    [-] 签到提交后未检测到明确结果")
    return False


# ── 已登录检测 ────────────────────────────────────────────────────────────────

def check_logged_in(page, site_config: dict) -> bool:
    site_url = site_config["url"]
    page.goto(site_url, wait_until="domcontentloaded", timeout=60000)
    time.sleep(3)

    if not wait_past_cf(page, timeout=120):
        return False

    return page.evaluate("""() => {
        const body = document.body ? document.body.innerText : '';
        if (body.includes('已登陆') || body.includes('控制面板') || body.includes('用户面板')) return true;
        for (const a of document.querySelectorAll('a')) {
            if (a.href && (a.href.includes('userdetails') || a.href.includes('logout')))
                return true;
        }
        return false;
    }""")


# ── 单站点处理 ────────────────────────────────────────────────────────────────

def process_site(site_config: dict) -> bool:
    name = site_config["name"]
    print(f"\n{'=' * 50}")
    print(f"  站点：{name} ({site_config['url']})")
    print(f"{'=' * 50}")

    # 从环境变量读取代理配置（选填）
    proxy_url = os.getenv("PROXY_URL")
    if proxy_url:
        print(f"    [*] 使用代理: {proxy_url}")
    else:
        print("    [*] 未配置代理，使用直连")

    context = launch_persistent_context(
        user_data_dir=get_profile_dir(name),
        headless=False,
        proxy=proxy_url if proxy_url else None,  # 只有配置了才传代理
        geoip=True if proxy_url else False,      # 只有使用代理时才启用 geoip
        locale="zh-CN",
        timezone="Asia/Shanghai",
        humanize=True,
        human_preset="careful",
        viewport={"width": 1920, "height": 1080},
        args=[
            "--disable-features=TrustedTypes",
            f"--fingerprint=checkin_{name}",
            "--fingerprint-noise=false",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1920,1080",
            "--start-maximized",
        ],
    )
    page = context.new_page()

    try:
        has_cookies = load_cookies(context, name)
        logged_in = has_cookies and check_logged_in(page, site_config)

        if not logged_in:
            print("    [!] 未登录，尝试登录...")
            if not login(page, site_config):
                return False

        return do_checkin(page, site_config)

    except Exception as e:
        print(f"    [-] 错误：{e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        context.close()


# ── 主函数 ────────────────────────────────────────────────────────────────────

def main():
    config = load_config()
    sites = build_sites(config)

    if not sites:
        print("[!] config.json 中没有启用的站点，请运行 run.sh --setup 添加站点。")
        sys.exit(1)

    # 支持只对单个站点签到：python checkin.py <site_name>
    if len(sys.argv) > 1:
        target = sys.argv[1]
        sites = [s for s in sites if s["name"] == target]
        if not sites:
            names = [s["name"] for s in build_sites(config)]
            print(f"[!] 未知站点：{target}")
            print(f"    可用站点：{', '.join(names)}")
            sys.exit(1)

    print("=" * 50)
    print("  Cloak Browser 自动签到助手")
    print("=" * 50)

    results: dict[str, str] = {}
    for site in sites:
        try:
            ok = process_site(site)
            results[site["name"]] = "OK" if ok else "FAIL"
        except Exception as e:
            results[site["name"]] = f"ERR: {e}"

    print(f"\n{'=' * 50}")
    print("  签到结果汇总")
    print(f"{'=' * 50}")
    
    # 统计结果并构建通知内容
    success_count = 0
    fail_count = 0
    details = []
    
    for name, status in results.items():
        icon = "✓" if status == "OK" else "✗"
        print(f"  {icon} {name}: {status}")
        if status == "OK":
            success_count += 1
        else:
            fail_count += 1
        details.append(f"{icon} {name}: {status}")
    
    # 发送 Bark 通知
    if success_count > 0 or fail_count > 0:
        is_critical = (fail_count > 0)
        
        if is_critical:
            title = f" PT签到异常 - 失败 {fail_count} 个站点"
            body = "\n".join(details)
        else:
            title = f" PT签到完成 - 全部成功 ({success_count} 个站点)"
            body = "\n".join(details)
        
        send_bark_notification(title, body, is_critical)


if __name__ == "__main__":
    main()
