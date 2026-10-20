# Physics Studio

Turn a topic file into a finished vertical lesson video (1080x1920, 30fps)
for TikTok, YouTube Shorts and Instagram Reels. 100% free, no API keys, no
watermarks. Built for the Real World Physics channel (WAEC / IGCSE / SAT
physics, simple English, real-life examples).

```
topic.json  -->  lesson cards (PIL)  -->  voiceover (edge-tts)  -->  final.mp4 (FFmpeg)
```

## Quick start

```bash
pip install -r requirements.txt
python physics_studio.py video topics/example_motion.json -o motion.mp4
```

That is the whole pipeline. The example topic produces a complete lesson.

## Dashboard (web UI)

Don't want to hand-edit JSON? Run the built-in dashboard:

```bash
python webui.py            # then open http://localhost:8000
```

Fill the form (title, voice, hook, cards, optional photos), click
**Build video**, and the finished MP4 appears with a download link and
inline preview. No extra dependencies: Python stdlib only. Builds run in
the background and land in `out/`, with the generated topic JSON kept in
`topics/web_<id>.json` for reference.

## Topic file format

```json
{
  "voice": "en-US-AndrewNeural",
  "hook_video": "my_hook_clip.mp4",   // optional: a real (stock or AI) clip
  "hook": { "narration": "opening line spoken over the clip" },
  "cards": [
    {
      "label": "Definition",           // yellow pill above the headline
      "title": "Motion is a change of position",
      "rows": [
        { "text": "Something moves when its position changes" },
        { "text": "A tree in the yard", "badge": "NO MOTION", "tone": "bad" }
      ],
      "note": "gray footnote shown at the bottom of the card",
      "narration": "exact words spoken while this card is on screen"
    }
  ]
}
```

- `tone: "good"` renders a green badge, `"bad"` a red one. Omit `badge` for
  plain rows.
- No burned-in captions on purpose: add auto-captions in CapCut after
  export, so you keep full control of the caption style.
- Optional hook clip: drop any 9:16 (or wider) clip next to the topic file
  and point `hook_video` at it. It is narrated over, scaled to 1080x1920 and
  held on its last frame if the narration runs longer than the clip.
- Optional `photo` on any card: a real-life photo band (path relative to the
  repo, e.g. `photos/track.jpg`). Real-life things while explaining is the
  channel's differentiator.

## Voices

`edge-tts` gives you Microsoft's free neural voices, no account needed.
Good teaching voices: `en-US-AndrewNeural` (warm, male), `en-GB-SoniaNeural`
(clear, female), `en-NG-EzinneNeural` / `en-NG-AbeoNeural` (Nigerian accent).
List everything with `python -m edge_tts --list-voices`.

## Requirements

- Python 3.9+
- FFmpeg on your PATH (`sudo apt install ffmpeg`, or set `FFMPEG_PATH`)
- Fonts: DejaVu ships with matplotlib and is auto-detected. Set `FONT_PATH`,
  `FONT_BOLD`, `FONT_REG` to use your own (e.g. Poppins for a friendlier look).

## Roadmap

- [ ] word-synced captions (optional, off by default)
- [ ] topic -> script draft with a free local LLM (no paid APIs, ever)
- [ ] YouTube auto-upload (needs your own Google Cloud OAuth consent)

## License

MIT
