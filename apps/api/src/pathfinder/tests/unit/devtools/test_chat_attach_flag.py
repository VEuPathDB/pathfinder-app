"""The debugger's ``--attach`` flag carries a local file into the turn's user
message the way the composer does: an inline file part after the text."""

from __future__ import annotations

import base64
from pathlib import Path
from uuid import uuid4

from pathfinder.devtools import chat
from pathfinder.devtools.gates import BodyCtx, attached_file, user_body

_PNG = b"\x89PNG\r\n\x1a\n"


def test_the_flag_is_parsed_once_per_file(tmp_path: Path) -> None:
    argv = ["hi", "--site", "plasmodb", "--run-dir", str(tmp_path)]

    parsed = chat.parse_run_args([*argv, "--attach", "a.png", "--attach", "b.pdf"])

    assert parsed.attachments == [Path("a.png"), Path("b.pdf")]
    assert chat.parse_run_args(argv).attachments == []


def test_a_file_is_attached_inline_with_the_media_type_its_name_gives(
    tmp_path: Path,
) -> None:
    path = tmp_path / "gene-table.png"
    path.write_bytes(_PNG)

    part = attached_file(path)

    assert (part.filename, part.media_type) == ("gene-table.png", "image/png")
    assert part.url == f"data:image/png;base64,{base64.b64encode(_PNG).decode()}"


def test_the_user_body_carries_the_text_then_each_file(tmp_path: Path) -> None:
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"%PDF-1.4")
    ctx = BodyCtx(conversation_id=uuid4(), site_id="plasmodb")

    body = user_body(
        ctx, message_id=uuid4(), text="which genes?", files=[attached_file(path)]
    )

    assert [p.type for p in body.messages[0].parts] == ["text", "file"]
    assert [f.filename for f in body.last_user_files] == ["paper.pdf"]
