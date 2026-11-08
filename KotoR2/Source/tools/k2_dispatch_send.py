"""Test client for the KOTOR 2 delivery dispatcher (nss/k2se_disp.nss). Plays the part the Archipelago client will play.

It writes one job at a time into %LOCALAPPDATA%\\K2SE\\ap\\inbox.txt (atomic replace) and reads the game's answers from ap\\outbox.txt.

  python tools/k2_dispatch_send.py send --seq 1 --action notify --msg "Hello from Archipelago"
  python tools/k2_dispatch_send.py demo            # sends a short scripted queue, one job after the previous one is acknowledged
  python tools/k2_dispatch_send.py watch           # prints new outbox lines as they appear
  python tools/k2_dispatch_send.py clear           # deletes inbox and outbox (game closed or not)

Outbox lines: D|seq|action|counter (applied), U|seq|counter (already applied), S|seq|counter (out of order: resend from counter+1),
G|seq|saved|job (other seed), W|seq|reason (refused).
"""
import argparse
import os
import sys
import time

AP = os.path.join(os.environ["LOCALAPPDATA"], "K2SE", "ap")
INBOX = os.path.join(AP, "inbox.txt")
OUTBOX = os.path.join(AP, "outbox.txt")


def write_job(seq, guard, action, args, msg):
    os.makedirs(AP, exist_ok=True)
    text = "job_seq=%d\njob_guard=%d\njob_action=%s\njob_args=%s\njob_msg=%s\n" % (seq, guard, action, args, msg)
    tmp = INBOX + ".tmp"
    with open(tmp, "w", newline="\n", encoding="ascii", errors="replace") as f:
        f.write(text)
    os.replace(tmp, INBOX)


def read_outbox():
    try:
        with open(OUTBOX, "r", encoding="ascii", errors="replace") as f:
            return [ln.rstrip("\r\n") for ln in f if ln.strip()]
    except FileNotFoundError:
        return []


def wait_for(seq, start_index, timeout):
    """Returns the first outbox line after start_index that mentions this seq, or None."""
    end = time.time() + timeout
    while time.time() < end:
        lines = read_outbox()
        for ln in lines[start_index:]:
            parts = ln.split("|")
            if len(parts) >= 3 and parts[2] == str(seq):
                return ln
        time.sleep(0.5)
    return None


def cmd_demo(args):
    jobs = [
        ("notify", "", "Archipelago test one: a message with nothing attached."),
        ("credits", "500", "Archipelago: you received 500 credits."),
        ("xp", "200", "Archipelago: you received 200 experience."),
        ("item", "g_i_medeqpmnt01", "Archipelago: you received a medical kit."),
    ]
    seq = args.start
    i = 0
    while i < len(jobs):
        action, a, msg = jobs[i]
        before = len(read_outbox())
        write_job(seq, args.guard, action, a, msg)
        print("sent job %d (%s %s); waiting for the game (it polls every few seconds when the moment is calm)..." % (seq, action, a))
        ln = wait_for(seq, before, args.timeout)
        if ln is None:
            print("  no answer within %d s. Is the game running with stage=60, and is the player free (no fight or conversation)?" % args.timeout)
            return 1
        print("  game says:", ln)
        kind = ln.split("|")[1]
        if kind == "D" or kind == "U":
            i += 1
            seq = seq % 255 + 1
        elif kind == "S":
            counter = int(ln.split("|")[3])
            print("  out of order: the save has counter %d, resending from %d" % (counter, counter % 255 + 1))
            seq = counter % 255 + 1
        else:
            return 1
        time.sleep(1.0)
    print("demo finished")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send")
    s.add_argument("--seq", type=int, required=True)
    s.add_argument("--guard", type=int, default=7)
    s.add_argument("--action", required=True)
    s.add_argument("--args", default="")
    s.add_argument("--msg", default="")
    d = sub.add_parser("demo")
    d.add_argument("--start", type=int, default=1)
    d.add_argument("--guard", type=int, default=7)
    d.add_argument("--timeout", type=int, default=60)
    sub.add_parser("watch")
    sub.add_parser("clear")
    a = ap.parse_args()
    if a.cmd == "send":
        write_job(a.seq, a.guard, a.action, a.args, a.msg)
        print("job written to", INBOX)
    elif a.cmd == "demo":
        return cmd_demo(a)
    elif a.cmd == "watch":
        seen = 0
        while True:
            lines = read_outbox()
            for ln in lines[seen:]:
                print(ln)
            seen = len(lines)
            time.sleep(0.5)
    elif a.cmd == "clear":
        for p in (INBOX, OUTBOX):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
        print("cleared")
    return 0


sys.exit(main())
