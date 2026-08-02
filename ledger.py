"""
[為什麼] 使用者想戒賭。把每一場的輸贏手動記下來、看見累積的真實數字，
         是面對賭博傷害最有效的方法之一。這支程式只做記錄與統計，
         不擷取任何賭場畫面、不給任何下注建議。
[怎麼做] 純手動輸入每場的「帶多少錢進去 / 帶多少錢出來」，存成本機 JSON。
         隨時可看累積淨輸贏、最慘的一場、連輸紀錄、以及這些錢原本能做什麼。
[結果]   一個誠實的帳本。數字幾乎一定是負的——那就是重點。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

# Windows 主機預設 cp950，中文輸入/輸出會亂碼或報錯。強制 UTF-8。
for _stream in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass  # 舊版 Python 或已被重導向時略過

LEDGER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions.json")
CLEAN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clean_days.json")


# ---------- 資料存取 ----------

def load_sessions() -> list[dict]:
    if not os.path.isfile(LEDGER_PATH):
        return []
    try:
        with open(LEDGER_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        print("[ERROR] 帳本檔案讀取失敗，當作空的處理。")
        return []


def save_sessions(sessions: list[dict]) -> None:
    with open(LEDGER_PATH, "w", encoding="utf-8") as fh:
        json.dump(sessions, fh, ensure_ascii=False, indent=2)


def load_clean_days() -> list[str]:
    """回傳有戒賭紀錄的日期清單（去重、排序）。"""
    if not os.path.isfile(CLEAN_PATH):
        return []
    try:
        with open(CLEAN_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return sorted(set(data)) if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_clean_days(days: list[str]) -> None:
    with open(CLEAN_PATH, "w", encoding="utf-8") as fh:
        json.dump(sorted(set(days)), fh, ensure_ascii=False, indent=2)


def current_streak(days: list[str]) -> int:
    """從今天往回數，連續有紀錄的天數。"""
    if not days:
        return 0
    from datetime import date, timedelta

    have = set(days)
    today = date.today()
    # 允許「昨天有記、今天還沒記」仍算連續
    start = today if today.isoformat() in have else today - timedelta(days=1)
    streak = 0
    cursor = start
    while cursor.isoformat() in have:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


# ---------- 輸入輔助 ----------

def safe_input(prompt: str) -> str:
    """包一層 input，遇到 EOF / Ctrl-C 回空字串而不是崩潰。"""
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def ask_number(prompt: str) -> float | None:
    raw = safe_input(prompt).strip()
    if raw == "":
        return None
    raw = raw.replace(",", "").replace("，", "")
    try:
        return float(raw)
    except ValueError:
        print("[ERROR] 請輸入數字。")
        return ask_number(prompt)


def ask_date(prompt: str) -> str:
    raw = safe_input(prompt).strip()
    if raw == "":
        return datetime.now().strftime("%Y-%m-%d")
    # 只做基本檢查，格式錯就沿用原字串，不擋使用者
    return raw


# ---------- 指令 ----------

def cmd_add(sessions: list[dict]) -> None:
    print("\n--- 記一場 ---")
    date = ask_date("日期（直接 Enter = 今天）: ")
    buy_in = ask_number("帶多少錢進去: ")
    if buy_in is None:
        print("[取消] 沒有輸入金額。")
        return
    cash_out = ask_number("帶多少錢出來（全輸就打 0）: ")
    if cash_out is None:
        print("[取消] 沒有輸入金額。")
        return

    net = cash_out - buy_in
    note = safe_input("備註（可留空，例如：心情、地點）: ").strip()

    sessions.append(
        {
            "date": date,
            "buy_in": buy_in,
            "cash_out": cash_out,
            "net": net,
            "note": note,
            "recorded_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    save_sessions(sessions)

    if net < 0:
        print(f"\n[記錄完成] 這場輸了 {abs(net):,.0f}。")
    elif net > 0:
        print(f"\n[記錄完成] 這場贏了 {net:,.0f}。（記得：長期莊家一定贏）")
    else:
        print("\n[記錄完成] 這場打平。")

    _print_running_total(sessions)


def cmd_list(sessions: list[dict]) -> None:
    if not sessions:
        print("\n還沒有任何紀錄。")
        return
    print("\n--- 所有紀錄 ---")
    print(f"{'日期':<12}{'進':>10}{'出':>10}{'淨':>12}  備註")
    print("-" * 60)
    for s in sessions:
        print(
            f"{s['date']:<12}{s['buy_in']:>10,.0f}{s['cash_out']:>10,.0f}"
            f"{s['net']:>+12,.0f}  {s.get('note', '')}"
        )


def cmd_stats(sessions: list[dict]) -> None:
    if not sessions:
        print("\n還沒有任何紀錄，先用 add 記一場。")
        return

    nets = [s["net"] for s in sessions]
    total_net = sum(nets)
    total_buy_in = sum(s["buy_in"] for s in sessions)
    n = len(sessions)
    wins = sum(1 for x in nets if x > 0)
    losses = sum(1 for x in nets if x < 0)
    worst = min(nets)
    best = max(nets)

    # 最長連輸
    longest_loss_streak = cur = 0
    for x in nets:
        if x < 0:
            cur += 1
            longest_loss_streak = max(longest_loss_streak, cur)
        else:
            cur = 0

    streak = current_streak(load_clean_days())

    print("\n========== 你的賭博總帳 ==========")
    if streak > 0:
        print(f"★ 連續戒賭     : {streak} 天")
        print("-" * 34)
    win_rate = wins / n * 100 if n else 0.0
    print(f"總場數         : {n}")
    print(f"贏的場數       : {wins}")
    print(f"輸的場數       : {losses}")
    print(f"勝率           : {win_rate:.1f}%")
    print(f"最長連輸       : {longest_loss_streak} 場")
    print(f"最慘的一場     : {worst:+,.0f}")
    print(f"最好的一場     : {best:+,.0f}")
    print("-" * 34)
    print(f"總共投入       : {total_buy_in:,.0f}")
    print(f"當前輸贏       : {total_net:+,.0f}")

    if total_net < 0:
        loss = abs(total_net)
        print("\n--- 這些錢原本可以 ---")
        print(f"到現在你淨輸了 {loss:,.0f}。")
        # 以台灣常見物價換算，讓數字變具體
        for label, price in (("頓 300 元的飯", 300), ("本書", 400), ("個月房租(以15000計)", 15000)):
            if price <= loss:
                print(f"  = {loss / price:,.0f} {label}")
        print("\n數字不會騙人。長期玩下去，這條線只會往下。")
        print("想找人談（免費、保密，雇主與保險查不到）：")
        print("  安心專線 1925 ・ 張老師 1980")
        print("  台北市立聯合醫院松德院區 博弈門診 (02)2726-3141 轉 1140")
    elif total_net > 0:
        print("\n目前帳面是正的。但這不是實力，是還沒還回去。")
        print("莊家的優勢是數學，時間站在莊家那邊，不是你。")
    print("==================================")


def cmd_clean(days: list[str]) -> None:
    """記錄今天沒有賭。"""
    today = datetime.now().strftime("%Y-%m-%d")
    if today in days:
        print(f"\n今天（{today}）已經記過了。")
    else:
        days.append(today)
        save_clean_days(days)
        print(f"\n[記錄完成] 今天 {today} 忍住了，沒賭。")
    streak = current_streak(days)
    print(f"\n  ★ 連續戒賭 {streak} 天 ★")
    if streak >= 1:
        print(f"  這 {streak} 天，你沒有讓任何錢流進莊家口袋。")
    milestones = {7: "一週", 30: "一個月", 100: "一百天", 365: "一年"}
    if streak in milestones:
        print(f"\n  === 里程碑：連續 {milestones[streak]}！這很了不起。===")


def _print_running_total(sessions: list[dict]) -> None:
    total = sum(s["net"] for s in sessions)
    print(f"[累積至今] 淨 {total:+,.0f}（共 {len(sessions)} 場）")


def cmd_help() -> None:
    print(
        """
賭博帳本 - 只記錄，不下注建議

用法:
  python ledger.py add     記一場（帶進 / 帶出）
  python ledger.py clean   記錄今天沒賭（累積戒賭天數）
  python ledger.py list    看所有紀錄
  python ledger.py stats   看總統計
  python ledger.py help    這個說明

資料存在同資料夾的 sessions.json，只在你自己電腦裡。
"""
    )


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "menu"
    sessions = load_sessions()

    if cmd == "add":
        cmd_add(sessions)
    elif cmd == "clean":
        cmd_clean(load_clean_days())
    elif cmd == "list":
        cmd_list(sessions)
    elif cmd == "stats":
        cmd_stats(sessions)
    elif cmd in ("help", "-h", "--help"):
        cmd_help()
    elif cmd == "menu":
        # 無參數時給互動選單，最簡單好用
        while True:
            print("\n[1] 記一場  [2] 今天沒賭  [3] 看紀錄  [4] 看統計  [5] 離開")
            choice = safe_input("選: ").strip()
            if choice == "1":
                cmd_add(sessions)
            elif choice == "2":
                cmd_clean(load_clean_days())
            elif choice == "3":
                cmd_list(sessions)
            elif choice == "4":
                cmd_stats(sessions)
            elif choice in ("5", "q", ""):
                print("再見。少賭一場就是賺一場。")
                break
            else:
                print("[ERROR] 請輸入 1-5。")
    else:
        print(f"[ERROR] 不認識的指令: {cmd}")
        cmd_help()
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
