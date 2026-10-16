"""Small context rules adapted from spending-effort-with-jev's judge.ts.

Copyright (c) 2026 Yaxin Luo. Adaptations copyright (c) 2026 Auto Effort contributors.
SPDX-License-Identifier: MIT. See the bundled third-party license and THIRD_PARTY.md.
"""

GO_AHEADS = frozenset({
    "ok", "okay", "k", "kk", "yes", "y", "yep", "yeah", "sure", "go", "go on",
    "go ahead", "continue", "proceed", "do it", "lgtm", "sounds good",
    "继续", "继续吧", "好", "好的", "行", "可以", "嗯", "对", "是", "开始", "开始吧",
})


def is_go_ahead(text: str) -> bool:
    """A known bare confirmation has no new task to classify by itself."""
    return text.lower().strip(" \t\r\n.!。！~～") in GO_AHEADS
