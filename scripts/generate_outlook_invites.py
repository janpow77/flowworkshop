#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import re
import shutil
import struct
import unicodedata
import zipfile
from dataclasses import dataclass
from email.message import EmailMessage
from email.policy import SMTP
from pathlib import Path

from extract_msg.ole_writer import OleWriter


SUBJECT_FALLBACK = (
    "Prueferworkshop 2026 in Hannover - Ihr persoenlicher Zugang zum Online-Tool"
)


@dataclass
class Invite:
    number: int
    name: str
    organization: str
    email: str
    link: str
    body: str


def strip_markdown_inline(text: str) -> str:
    text = text.replace("**", "")
    text = text.replace("„", '"').replace("“", '"')
    return text


def parse_invites(path: Path) -> tuple[str, list[Invite]]:
    text = path.read_text(encoding="utf-8")
    subject_match = re.search(r"\*\*Betreff:\*\*\s*(.+)", text)
    subject = (
        strip_markdown_inline(subject_match.group(1)).strip()
        if subject_match
        else SUBJECT_FALLBACK
    )

    heading_re = re.compile(
        r"^##\s+(\d+)\.\s+(.+?)(?:\s+\((.*?)\))?\s*$",
        re.MULTILINE,
    )
    matches = list(heading_re.finditer(text))
    invites: list[Invite] = []

    for index, match in enumerate(matches):
        number = int(match.group(1))
        name = match.group(2).strip()
        organization = (match.group(3) or "").strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end]

        if "Zusammenfassung" in name:
            continue

        email_match = re.search(r"\*\*An:\*\*\s*(\S+)", block)
        link_match = re.search(r"\*\*Einladungslink:\*\*\s*(\S+)", block)
        if not email_match or not link_match:
            continue

        body_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith(">"):
                line = line[1:]
                if line.startswith(" "):
                    line = line[1:]
                body_lines.append(strip_markdown_inline(line).rstrip())

        while body_lines and not body_lines[0]:
            body_lines.pop(0)
        while body_lines and not body_lines[-1]:
            body_lines.pop()

        invites.append(
            Invite(
                number=number,
                name=name,
                organization=organization,
                email=email_match.group(1).strip(),
                link=link_match.group(1).strip(),
                body="\n".join(body_lines),
            )
        )

    return subject, invites


def safe_stem(invite: Invite) -> str:
    normalized = unicodedata.normalize("NFKD", invite.name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^A-Za-z0-9]+", "_", ascii_name).strip("_")
    return f"{invite.number:02d}_{ascii_name or 'Einladung'}"


def unicode_stream(value: str) -> bytes:
    return value.encode("utf-16-le")


def binary_stream(value: bytes) -> bytes:
    return value


def fixed_prop(name: str, value: int | bool) -> bytes:
    prop_id = int(name[:4], 16)
    prop_type = int(name[4:], 16)
    tag = struct.pack("<HHI", prop_type, prop_id, 0)
    if prop_type == 0x000B:
        raw_value = struct.pack("<H", 1 if value else 0) + b"\x00" * 6
    elif prop_type == 0x0003:
        raw_value = struct.pack("<I", int(value)) + b"\x00" * 4
    else:
        raw_value = b"\x00" * 8
    return tag + raw_value


def variable_prop(name: str) -> bytes:
    prop_id = int(name[:4], 16)
    prop_type = int(name[4:], 16)
    tag = struct.pack("<HHI", prop_type, prop_id, 0)
    if prop_type == 0x001F:
        tail = b"\x02\x00\x00\x00\x00\x00\x00\x00"
    elif prop_type == 0x0102:
        tail = b"\x00" * 8
    else:
        tail = b"\x00" * 8
    return tag + tail


def message_props(recipient_count: int) -> bytes:
    props = [
        fixed_prop("00170003", 1),       # PR_IMPORTANCE: normal
        variable_prop("001A001F"),       # PR_MESSAGE_CLASS_W
        fixed_prop("00260003", 0),       # PR_PRIORITY: normal
        variable_prop("0037001F"),       # PR_SUBJECT_W
        variable_prop("0070001F"),       # PR_CONVERSATION_TOPIC_W
        variable_prop("007D001F"),       # PR_TRANSPORT_MESSAGE_HEADERS_W
        fixed_prop("0E070003", 8),       # PR_MESSAGE_FLAGS: unsent draft
        variable_prop("0E04001F"),       # PR_DISPLAY_TO_W
        fixed_prop("0E1B000B", False),   # PR_HASATTACH
        variable_prop("1000001F"),       # PR_BODY_W
        variable_prop("10130102"),       # PR_HTML
        fixed_prop("340D0003", 0x40000), # PR_STORE_SUPPORT_MASK: Unicode
    ]
    header = b"\x00" * 8 + struct.pack("<4I", recipient_count, 0, recipient_count, 0)
    header += b"\x00" * 8
    return header + b"".join(props)


def recipient_props() -> bytes:
    props = [
        fixed_prop("0C150003", 1),       # PR_RECIPIENT_TYPE: To
        fixed_prop("0FFE0003", 6),       # PR_OBJECT_TYPE: mail user
        variable_prop("3001001F"),       # PR_DISPLAY_NAME_W
        variable_prop("3002001F"),       # PR_ADDRTYPE_W
        variable_prop("3003001F"),       # PR_EMAIL_ADDRESS_W
        variable_prop("300B0102"),       # PR_SEARCH_KEY
        fixed_prop("39000003", 0),       # PR_DISPLAY_TYPE
        variable_prop("39FE001F"),       # PR_SMTP_ADDRESS_W
    ]
    return b"\x00" * 8 + b"".join(props)


def body_to_html(body: str) -> str:
    paragraphs: list[str] = []
    for para in re.split(r"\n\s*\n", body.strip()):
        escaped = html.escape(para).replace("\n", "<br>")
        escaped = re.sub(
            r"(https://[^\s<]+)",
            r'<a href="\1">\1</a>',
            escaped,
        )
        paragraphs.append(f"<p>{escaped}</p>")
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"></head>"
        "<body style=\"font-family:Calibri,Arial,sans-serif;font-size:11pt;\">"
        + "\n".join(paragraphs)
        + "</body></html>"
    )


def write_msg(invite: Invite, subject: str, path: Path) -> None:
    writer = OleWriter()
    recipient_dir = "__recip_version1.0_#00000000"
    body_html = body_to_html(invite.body)
    headers = (
        f"To: {invite.email}\r\n"
        f"Subject: {subject}\r\n"
        "X-Unsent: 1\r\n"
    )

    writer.addEntry("__properties_version1.0", message_props(1))
    writer.addEntry("__substg1.0_001A001F", unicode_stream("IPM.Note"))
    writer.addEntry("__substg1.0_0037001F", unicode_stream(subject))
    writer.addEntry("__substg1.0_0070001F", unicode_stream(subject))
    writer.addEntry("__substg1.0_007D001F", unicode_stream(headers))
    writer.addEntry("__substg1.0_0E04001F", unicode_stream(invite.email))
    writer.addEntry("__substg1.0_1000001F", unicode_stream(invite.body))
    writer.addEntry("__substg1.0_10130102", binary_stream(body_html.encode("utf-8")))

    writer.addEntry(recipient_dir, storage=True)
    writer.addEntry([recipient_dir, "__properties_version1.0"], recipient_props())
    writer.addEntry([recipient_dir, "__substg1.0_3001001F"], unicode_stream(invite.name))
    writer.addEntry([recipient_dir, "__substg1.0_3002001F"], unicode_stream("SMTP"))
    writer.addEntry([recipient_dir, "__substg1.0_3003001F"], unicode_stream(invite.email))
    writer.addEntry(
        [recipient_dir, "__substg1.0_300B0102"],
        binary_stream((f"SMTP:{invite.email}\x00").encode("ascii", "ignore")),
    )
    writer.addEntry([recipient_dir, "__substg1.0_39FE001F"], unicode_stream(invite.email))

    writer.write(path)


def write_eml(invite: Invite, subject: str, path: Path) -> None:
    msg = EmailMessage(policy=SMTP)
    msg["To"] = invite.email
    msg["Subject"] = subject
    msg["X-Unsent"] = "1"
    msg.set_content(invite.body)
    msg.add_alternative(body_to_html(invite.body), subtype="html")
    path.write_bytes(bytes(msg))


def write_index(subject: str, invites: list[Invite], out_dir: Path) -> None:
    lines = [
        "# Outlook-Einladungsentwuerfe",
        "",
        f"Betreff: {subject}",
        "",
        "| # | Name | E-Mail | Datei |",
        "|---|------|--------|-------|",
    ]
    for invite in invites:
        stem = safe_stem(invite)
        lines.append(
            f"| {invite.number} | {invite.name} | {invite.email} | msg/{stem}.msg |"
        )
    lines.append("")
    lines.append("Die .eml-Dateien im Ordner eml-fallback sind nur als Outlook-Fallback gedacht.")
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="einladungs-emails.md")
    parser.add_argument("--out", default="outlook-einladungen")
    args = parser.parse_args()

    source = Path(args.source)
    out_dir = Path(args.out)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    msg_dir = out_dir / "msg"
    eml_dir = out_dir / "eml-fallback"
    msg_dir.mkdir(parents=True)
    eml_dir.mkdir(parents=True)

    subject, invites = parse_invites(source)
    if not invites:
        raise SystemExit("No invites found.")

    for invite in invites:
        stem = safe_stem(invite)
        write_msg(invite, subject, msg_dir / f"{stem}.msg")
        write_eml(invite, subject, eml_dir / f"{stem}.eml")

    write_index(subject, invites, out_dir)

    zip_path = out_dir.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(out_dir.rglob("*")):
            zf.write(path, path.relative_to(out_dir.parent))

    print(f"Wrote {len(invites)} MSG files to {msg_dir}")
    print(f"Wrote fallback EML files to {eml_dir}")
    print(f"Wrote ZIP archive to {zip_path}")


if __name__ == "__main__":
    main()
