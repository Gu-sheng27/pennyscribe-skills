import json
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "repurpose-podcast"


def load_acquirer():
    spec = importlib.util.spec_from_file_location("acquire_media", SKILL / "scripts" / "acquire_media.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SkillScriptTests(unittest.TestCase):
    def test_public_page_fallback_downloads_and_normalizes_once(self):
        module = load_acquirer()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "source"

            def fake_download(_url, target):
                target.write_bytes(b"original-audio")

            def fake_normalize(source, target):
                self.assertEqual(source.read_bytes(), b"original-audio")
                target.write_bytes(b"normalized-audio")

            argv = [
                "acquire_media.py",
                "https://www.xiaoyuzhoufm.com/episode/example",
                "--output-dir",
                str(output),
            ]
            failed_probe = subprocess.CompletedProcess([], 1, "", "unsupported")
            with (
                mock.patch.object(module.shutil, "which", return_value="/usr/bin/tool"),
                mock.patch.object(module, "run", return_value=failed_probe),
                mock.patch.object(module, "apple_episode", return_value=(None, {})),
                mock.patch.object(module, "page_media", return_value=("https://cdn.example.com/episode.mp3", {"title": "Episode"})),
                mock.patch.object(module, "download", side_effect=fake_download) as downloader,
                mock.patch.object(module, "normalize", side_effect=fake_normalize) as normalizer,
                mock.patch.object(sys, "argv", argv),
            ):
                self.assertEqual(module.main(), 0)

            downloader.assert_called_once()
            normalizer.assert_called_once()
            self.assertEqual((output / "media.mp3").read_bytes(), b"normalized-audio")
            self.assertFalse((output / "download.mp3").exists())
            metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["platform"], "xiaoyuzhou")
            self.assertEqual(metadata["title"], "Episode")

    def test_resolves_apple_episode_with_public_lookup_metadata(self):
        module = load_acquirer()
        payload = {"results": [{"trackId": 456, "episodeUrl": "https://cdn.example.com/episode.mp3", "trackName": "Episode", "collectionName": "Show", "trackTimeMillis": 123000}]}
        response = subprocess.CompletedProcess([], 0, json.dumps(payload).encode(), b"")
        with mock.patch.object(module.subprocess, "run", return_value=response):
            media, metadata = module.apple_episode("https://podcasts.apple.com/us/podcast/example/id123?i=456")
        self.assertEqual(media, "https://cdn.example.com/episode.mp3")
        self.assertEqual(metadata["creator"], "Show")
        self.assertEqual(metadata["duration_seconds"], 123)

    def test_builds_self_contained_workspace_with_five_views(self):
        project = {
            "schema_version": 1,
            "source": {"url": "https://example.com/episode", "platform": "test", "title": "A useful conversation", "creator": "Example Show", "cover": None},
            "transcript": {"raw": "第一段完整内容。第二段完整内容。", "readable": {"title": "整理后的全文", "dek": "导语", "sections": [{"id": "section-01", "heading": "开始", "paragraphs": [{"id": "p-001", "text": "第一段完整内容。", "source_start": 0, "source_end": 8}]}]}},
            "digest": {"recommendation": "值得阅读", "summary": "摘要", "insights": [{"text": "观点", "source_paragraph_ids": ["p-001"]}], "quotes": [{"text": f"金句 {index}", "fidelity": "verbatim", "source_paragraph_ids": ["p-001"]} for index in range(1, 4)], "audience": ["创作者"]},
            "x": {"single_posts": [{"text": "一条 X https://example.com/episode", "source_paragraph_ids": ["p-001"]}], "threads": []},
            "xiaohongshu": {"title_options": ["更适合传播的新标题"], "caption": "第一段发布文案。\n\n第二段发布文案。", "theme": "editorial-red", "cards": [{"kind": "cover" if index == 1 else "insight", "eyebrow": "PODCAST NOTES", "title": f"卡片标题 {index}", "body": "卡片正文", "source_paragraph_ids": ["p-001"]} for index in range(1, 5)]},
        }
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "project.json"
            target = Path(directory) / "index.html"
            source.write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run([sys.executable, str(SKILL / "scripts" / "build_workspace.py"), str(source), "--output", str(target)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            html = target.read_text(encoding="utf-8")
            for text in ("导读与摘要", "金句", "阅读全文", "X 素材", "小红书素材", "第一段完整内容。", "卡片标题", "导出全部卡片", "复制文字"):
                self.assertIn(text, html)
            self.assertNotIn("__PROJECT_DATA__", html)

            validation = subprocess.run([sys.executable, str(SKILL / "scripts" / "validate_project.py"), str(source)], capture_output=True, text=True)
            self.assertEqual(validation.returncode, 0, validation.stderr)

    def test_builds_switchable_local_library(self):
        def project(number):
            return {
                "schema_version": 1,
                "source": {"url": f"https://example.com/episode-{number}", "platform": "test", "title": f"Episode {number}", "creator": "Example Show", "cover": None},
                "transcript": {"raw": "完整内容。", "readable": {"title": f"Readable {number}", "dek": "导语", "sections": []}},
                "digest": {"recommendation": "值得阅读", "summary": "摘要", "insights": [], "quotes": [], "audience": []},
                "x": {"single_posts": [], "threads": []},
                "xiaohongshu": {"title_options": [], "caption": "", "theme": "editorial-red", "cards": []},
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = []
            for number in (1, 2):
                path = root / f"project-{number}.json"
                path.write_text(json.dumps(project(number), ensure_ascii=False), encoding="utf-8")
                sources.append(path)
            output = root / "library"
            result = subprocess.run([sys.executable, str(SKILL / "scripts" / "build_site.py"), *(str(path) for path in sources), "--output-dir", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            index = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("切换播客", index)
            self.assertIn("Episode 1", index)
            self.assertIn("Episode 2", index)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest), 2)
            for item in manifest:
                self.assertTrue((output / item["file"]).exists())

    def test_acquires_and_normalizes_local_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.wav"
            output = Path(directory) / "source"
            generated = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2", str(source)], capture_output=True, text=True)
            self.assertEqual(generated.returncode, 0, generated.stderr)
            result = subprocess.run([sys.executable, str(SKILL / "scripts" / "acquire_media.py"), str(source), "--output-dir", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertGreater((output / "media.mp3").stat().st_size, 0)
            metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["platform"], "local-file")


if __name__ == "__main__":
    unittest.main()
