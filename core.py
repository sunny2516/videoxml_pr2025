"""
core.py — PR XML 生成工具核心逻辑
负责：SRT解析 / 镜头文件扫描 / 关键词匹配 / XML生成
"""

import os
import re
import uuid
import random
import json
from pathlib import Path
from urllib.parse import quote
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple


# ─────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────

@dataclass
class SRTEntry:
    index: int
    start_sec: float   # 开始时间（秒）
    end_sec: float     # 结束时间（秒）
    text: str

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec


@dataclass
class ClipPair:
    """一组口播：视频文件 + SRT文件"""
    name: str           # 显示名称，如 "口播1"
    video_path: str     # 绝对路径
    srt_path: str       # 绝对路径


@dataclass
class FootageFolder:
    """镜头分类文件夹"""
    keyword: str        # 关键词（=文件夹名）
    folder_path: str    # 绝对路径
    files: List[str] = field(default_factory=list)   # 文件绝对路径列表

    def load_files(self):
        exts = {'.mp4', '.MP4', '.mov', '.MOV', '.avi', '.AVI'}
        self.files = [
            str(p) for p in Path(self.folder_path).iterdir()
            if p.suffix in exts
        ]

    def pick_random(self, exclude: List[str] = None) -> Optional[str]:
        """随机取一个，尽量不重复"""
        pool = [f for f in self.files if f not in (exclude or [])]
        if not pool:
            pool = self.files  # 全用完了就允许重复
        return random.choice(pool) if pool else None


@dataclass
class KeywordRule:
    """关键词映射规则"""
    keyword: str
    folder_path: str
    enabled: bool = True
    max_occurrences: int = 0   # 0=不限制，>0=最多插入N次


@dataclass
class ProjectConfig:
    """工程配置（持久化到JSON）"""
    name: str = ""
    footage_root: str = ""          # 镜头母文件夹
    keyword_rules: List[dict] = field(default_factory=list)
    output_dir: str = ""
    fps: int = 30
    width: int = 1080
    height: int = 1920
    # 历史口播文件夹列表（每次可多选）
    recent_kobo_dirs: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────
# SRT 解析
# ─────────────────────────────────────────────

def parse_srt(srt_path: str) -> List[SRTEntry]:
    """解析SRT文件，返回字幕条目列表"""
    entries = []
    text = Path(srt_path).read_text(encoding='utf-8-sig', errors='replace')
    # 支持 \r\n 和 \n
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    blocks = re.split(r'\n{2,}', text.strip())

    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
        # 第一行：序号
        try:
            idx = int(lines[0].strip())
        except ValueError:
            continue
        # 第二行：时间码
        time_match = re.match(
            r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})',
            lines[1].strip()
        )
        if not time_match:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = [int(x) for x in time_match.groups()]
        start = h1*3600 + m1*60 + s1 + ms1/1000
        end   = h2*3600 + m2*60 + s2 + ms2/1000
        # 剩余行：文本（去掉HTML标签）
        raw_text = ' '.join(lines[2:]).strip()
        clean_text = re.sub(r'<[^>]+>', '', raw_text)
        if clean_text:
            entries.append(SRTEntry(idx, start, end, clean_text))

    return entries


# ─────────────────────────────────────────────
# 文件夹扫描
# ─────────────────────────────────────────────

def scan_kobo_folder(folder_path: str) -> List[ClipPair]:
    """
    扫描口播文件夹，自动识别两种结构：
    - 有子文件夹：口播/子文件夹/视频.mp4 + 字幕.srt
    - 无子文件夹：口播/视频.mp4 + 字幕.srt
    返回按名称排序的 ClipPair 列表
    """
    root = Path(folder_path)
    pairs = []
    video_exts = {'.mp4', '.MP4', '.mov', '.MOV'}
    srt_exts = {'.srt', '.SRT'}

    def find_pair_in_dir(d: Path, display_name: str):
        videos = [f for f in d.iterdir() if f.suffix in video_exts]
        srts   = [f for f in d.iterdir() if f.suffix in srt_exts]
        if not videos or not srts:
            return
        # 优先按文件名匹配
        for v in videos:
            stem = v.stem
            matched = [s for s in srts if s.stem == stem]
            if matched:
                pairs.append(ClipPair(display_name, str(v), str(matched[0])))
                return
        # 没有同名就取第一个
        pairs.append(ClipPair(display_name, str(videos[0]), str(srts[0])))

    # 先看根目录是否有视频（无子文件夹结构）
    root_videos = [f for f in root.iterdir() if f.is_file() and f.suffix in video_exts]
    root_srts   = [f for f in root.iterdir() if f.is_file() and f.suffix in srt_exts]

    if root_videos and root_srts:
        # 无子文件夹：根目录直接有配对文件
        for v in sorted(root_videos, key=lambda x: x.name):
            stem = v.stem
            matched = [s for s in root_srts if s.stem == stem]
            if matched:
                pairs.append(ClipPair(v.stem, str(v), str(matched[0])))
    else:
        # 有子文件夹
        subdirs = sorted([d for d in root.iterdir() if d.is_dir()], key=lambda x: x.name)
        for sub in subdirs:
            find_pair_in_dir(sub, sub.name)

    return pairs


def scan_footage_root(footage_root: str) -> List[FootageFolder]:
    """扫描镜头母文件夹，返回所有子文件夹作为关键词分类"""
    root = Path(footage_root)
    result = []
    for d in sorted(root.iterdir()):
        if d.is_dir():
            ff = FootageFolder(keyword=d.name, folder_path=str(d))
            ff.load_files()
            result.append(ff)
    return result


# ─────────────────────────────────────────────
# 关键词匹配
# ─────────────────────────────────────────────

def match_keywords(
    entries: List[SRTEntry],
    rules: List[KeywordRule],
    footage_map: Dict[str, FootageFolder]
) -> List[Tuple[SRTEntry, str, str]]:
    """
    对每条SRT字幕做关键词匹配
    返回：[(SRTEntry, keyword, footage_file_path), ...]
    已使用素材会记录，尽量不重复
    occurrence_count记录每个关键词已匹配次数，用于max_occurrences限制
    """
    results = []
    used_files: Dict[str, List[str]] = {}     # keyword -> [已用文件]
    occurrence_count: Dict[str, int] = {}      # keyword -> 出现次数

    for entry in entries:
        for rule in rules:
            if not rule.enabled:
                continue
            kw = rule.keyword
            if kw not in occurrence_count:
                occurrence_count[kw] = 0

            # 检查最大次数
            max_occ = rule.max_occurrences
            if max_occ > 0 and occurrence_count[kw] >= max_occ:
                continue

            # 文字匹配（简单包含）
            if kw in entry.text:
                ff = footage_map.get(kw)
                if not ff or not ff.files:
                    continue
                used = used_files.get(kw, [])
                chosen = ff.pick_random(exclude=used)
                if chosen:
                    used_files.setdefault(kw, []).append(chosen)
                    occurrence_count[kw] += 1
                    results.append((entry, kw, chosen))
                break  # 一句话只匹配第一个命中的关键词

    return results


# ─────────────────────────────────────────────
# 时长计算（帧数）
# ─────────────────────────────────────────────

PPRO_TICKS_PER_FRAME = 8467200000  # PR内部tick单位


def sec_to_frames(sec: float, fps: int) -> int:
    return round(sec * fps)


def frames_to_ticks(frames: int) -> int:
    return frames * PPRO_TICKS_PER_FRAME


def calc_broll_in_out(
    entry_duration_sec: float,
    footage_duration_sec: float,
    fps: int
) -> Tuple[int, int]:
    """
    计算B-roll素材的 in/out 帧
    规则：
    - 素材 < 1秒：跳过（返回 None，调用方处理）
    - 素材时长 >= 口播时长：直接从头截取口播时长
    - 素材/口播 >= 75%：从素材头部截取
    - 素材/口播 < 75%：从素材尾部截取（保留素材全长，以尾部对齐）
    返回 (in_frame, out_frame) 基于素材自身帧率
    """
    if footage_duration_sec < 1.0:
        return None  # 跳过

    if footage_duration_sec >= entry_duration_sec:
        # 素材比口播长或相等，从头截取口播时长
        in_f = 0
        out_f = sec_to_frames(entry_duration_sec, fps)
    else:
        ratio = footage_duration_sec / entry_duration_sec
        if ratio >= 0.75:
            # 从素材头部截取（保留全部素材）
            in_f = 0
            out_f = sec_to_frames(footage_duration_sec, fps)
        else:
            # 从素材尾部截取（素材放在句尾）
            in_f = 0
            out_f = sec_to_frames(footage_duration_sec, fps)

    return (in_f, out_f)


def get_video_info(file_path: str) -> Tuple[int, int, int, int]:
    """
    读取视频基本信息（宽、高、帧率分子、帧率分母）
    简单实现：从文件名/路径无法读取，返回默认值
    实际使用时可用 ffprobe，这里先返回常见值
    返回 (width, height, timebase, is_ntsc)
    """
    # 尝试用 ffprobe（如果系统有）
    try:
        import subprocess, json as _json
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json',
             '-show_streams', file_path],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            data = _json.loads(result.stdout)
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    w = stream.get('width', 1080)
                    h = stream.get('height', 1920)
                    # 帧率
                    fr = stream.get('r_frame_rate', '30/1')
                    num, den = fr.split('/')
                    fps_val = int(num) / int(den)
                    # 判断NTSC（29.97近似30）
                    ntsc = abs(fps_val - 29.97) < 0.1 or abs(fps_val - 59.94) < 0.1
                    tb = round(fps_val)
                    dur_frames = stream.get('nb_frames')
                    return w, h, tb, ntsc, int(dur_frames) if dur_frames else None
    except Exception:
        pass
    return 1080, 1920, 30, False, None


def get_video_duration_frames(file_path: str, fallback_fps: int = 30) -> Optional[int]:
    """获取视频时长（帧数）"""
    w, h, tb, ntsc, dur = get_video_info(file_path)
    return dur  # 可能为None


# ─────────────────────────────────────────────
# 路径转 URL
# ─────────────────────────────────────────────

def path_to_url(abs_path: str) -> str:
    """
    Windows绝对路径转PR pathurl格式
    例：F:\\镜头\\OTC\\clip1.mp4
     -> file://localhost/F%3a/%e9%95%9c%e5%a4%b4/OTC/clip1.mp4
    """
    # 统一用正斜杠
    p = abs_path.replace('\\', '/')
    # 盘符处理：F: -> F%3a
    if re.match(r'^[A-Za-z]:', p):
        drive = p[0]
        rest = p[2:]  # 去掉冒号
        encoded = quote(rest, safe='/')
        return f"file://localhost/{drive}%3a{encoded}"
    else:
        return "file://localhost/" + quote(p, safe='/')


# ─────────────────────────────────────────────
# XML 生成
# ─────────────────────────────────────────────

_id_counter = 0

def new_id(prefix: str) -> str:
    global _id_counter
    _id_counter += 1
    return f"{prefix}-{_id_counter}"

def reset_id_counter():
    global _id_counter
    _id_counter = 0


SEQ_ATTRS = (
    'TL.SQAudioVisibleBase="0" TL.SQVideoVisibleBase="0" TL.SQVisibleBaseTime="0" '
    'TL.SQAVDividerPosition="0.5" TL.SQHideShyTracks="0" TL.SQHeaderWidth="204" '
    'Monitor.ProgramZoomOut="1998259200000" Monitor.ProgramZoomIn="0" '
    'TL.SQTimePerPixel="0.018762183235864725" MZ.EditLine="0" '
    'MZ.Sequence.PreviewFrameSizeHeight="{height}" MZ.Sequence.PreviewFrameSizeWidth="{width}" '
    'MZ.Sequence.AudioTimeDisplayFormat="200" '
    'MZ.Sequence.PreviewRenderingClassID="1061109567" '
    'MZ.Sequence.PreviewRenderingPresetCodec="1634755443" '
    'MZ.Sequence.PreviewRenderingPresetPath="EncoderPresets\\SequencePreview\\9678af98-a7b7-4bdb-b477-7ac9c8df4a4e\\QuickTime.epr" '
    'MZ.Sequence.PreviewUseMaxRenderQuality="false" '
    'MZ.Sequence.PreviewUseMaxBitDepth="false" '
    'MZ.Sequence.EditingModeGUID="9678af98-a7b7-4bdb-b477-7ac9c8df4a4e" '
    'MZ.Sequence.VideoTimeDisplayFormat="104" '
    'MZ.WorkOutPoint="{work_out}" MZ.WorkInPoint="0" explodedTracks="true"'
)

LOGGING_INFO = """
                <logginginfo>
                    <description></description>
                    <scene></scene>
                    <shottake></shottake>
                    <lognote></lognote>
                    <good></good>
                    <originalvideofilename></originalvideofilename>
                    <originalaudiofilename></originalaudiofilename>
                </logginginfo>
                <colorinfo>
                    <lut></lut>
                    <lut1></lut1>
                    <asc_sop></asc_sop>
                    <asc_sat></asc_sat>
                    <lut2></lut2>
                </colorinfo>"""

AUDIO_TRACK_ATTRS = (
    'TL.SQTrackAudioKeyframeStyle="0" TL.SQTrackShy="0" '
    'TL.SQTrackExpandedHeight="41" TL.SQTrackExpanded="0" MZ.TrackTargeted="1" '
    'PannerCurrentValue="0.5" PannerIsInverted="true" '
    'PannerStartKeyframe="-91445760000000000,0.5,0,0,0,0,0,0" '
    'PannerName="平衡" '
    'currentExplodedTrackIndex="{idx}" totalExplodedTrackCount="2" '
    'premiereTrackType="Stereo"'
)


def build_rate_xml(timebase: int, ntsc: bool, indent: str = "                ") -> str:
    ntsc_str = "TRUE" if ntsc else "FALSE"
    return f"""{indent}<rate>
{indent}    <timebase>{timebase}</timebase>
{indent}    <ntsc>{ntsc_str}</ntsc>
{indent}</rate>"""


def build_file_xml(
    file_id: str, file_path: str,
    w: int, h: int, tb: int, ntsc: bool, dur_frames: int,
    audio_depth: int = 16, audio_sr: int = 44100,
    indent: str = "            "
) -> str:
    name = Path(file_path).name
    url = path_to_url(file_path)
    ntsc_str = "TRUE" if ntsc else "FALSE"
    i = indent
    tc_str = "00:00:00:00"
    return f"""{i}<file id="{file_id}">
{i}    <name>{name}</name>
{i}    <pathurl>{url}</pathurl>
{i}    <rate>
{i}        <timebase>{tb}</timebase>
{i}        <ntsc>{ntsc_str}</ntsc>
{i}    </rate>
{i}    <duration>{dur_frames if dur_frames else 0}</duration>
{i}    <timecode>
{i}        <rate>
{i}            <timebase>{tb}</timebase>
{i}            <ntsc>{ntsc_str}</ntsc>
{i}        </rate>
{i}        <string>{tc_str}</string>
{i}        <frame>0</frame>
{i}        <displayformat>NDF</displayformat>
{i}    </timecode>
{i}    <media>
{i}        <video>
{i}            <samplecharacteristics>
{i}                <rate>
{i}                    <timebase>{tb}</timebase>
{i}                    <ntsc>{ntsc_str}</ntsc>
{i}                </rate>
{i}                <width>{w}</width>
{i}                <height>{h}</height>
{i}                <anamorphic>FALSE</anamorphic>
{i}                <pixelaspectratio>square</pixelaspectratio>
{i}                <fielddominance>none</fielddominance>
{i}            </samplecharacteristics>
{i}        </video>
{i}        <audio>
{i}            <samplecharacteristics>
{i}                <depth>{audio_depth}</depth>
{i}                <samplerate>{audio_sr}</samplerate>
{i}            </samplecharacteristics>
{i}            <channelcount>2</channelcount>
{i}        </audio>
{i}    </media>
{i}</file>"""


def generate_xml_for_clip(
    clip: ClipPair,
    rules: List[KeywordRule],
    footage_map: Dict[str, FootageFolder],
    fps: int = 30,
    seq_width: int = 1080,
    seq_height: int = 1920,
) -> str:
    """为单个口播生成完整的 xmeml XML 字符串"""
    reset_id_counter()

    entries = parse_srt(clip.srt_path)
    if not entries:
        raise ValueError(f"SRT文件为空或解析失败：{clip.srt_path}")

    # 口播视频信息
    v_w, v_h, v_tb, v_ntsc, v_dur = get_video_info(clip.video_path)
    # 如果无法读取时长，用SRT最后一条的结束时间估算
    if v_dur is None:
        v_dur = sec_to_frames(entries[-1].end_sec, fps)

    seq_id = new_id("sequence")
    seq_uuid = str(uuid.uuid4())
    work_out_ticks = frames_to_ticks(v_dur)

    seq_attr = SEQ_ATTRS.format(
        height=seq_height, width=seq_width, work_out=work_out_ticks
    )

    # 序列视频格式块
    def seq_format_xml():
        return f"""                <format>
                    <samplecharacteristics>
                        <rate>
                            <timebase>{fps}</timebase>
                            <ntsc>FALSE</ntsc>
                        </rate>
                        <codec>
                            <name>Apple ProRes 422</name>
                            <appspecificdata>
                                <appname>Final Cut Pro</appname>
                                <appmanufacturer>Apple Inc.</appmanufacturer>
                                <appversion>7.0</appversion>
                                <data>
                                    <qtcodec>
                                        <codecname>Apple ProRes 422</codecname>
                                        <codectypename>Apple ProRes 422</codectypename>
                                        <codectypecode>apcn</codectypecode>
                                        <codecvendorcode>appl</codecvendorcode>
                                        <spatialquality>1024</spatialquality>
                                        <temporalquality>0</temporalquality>
                                        <keyframerate>0</keyframerate>
                                        <datarate>0</datarate>
                                    </qtcodec>
                                </data>
                            </appspecificdata>
                        </codec>
                        <width>{seq_width}</width>
                        <height>{seq_height}</height>
                        <anamorphic>FALSE</anamorphic>
                        <pixelaspectratio>square</pixelaspectratio>
                        <fielddominance>none</fielddominance>
                        <colordepth>24</colordepth>
                    </samplecharacteristics>
                </format>"""

    # ── 口播 clipitem ID ──
    ci_video_id = new_id("clipitem")
    ci_audio1_id = new_id("clipitem")
    ci_audio2_id = new_id("clipitem")
    file_kobo_id = new_id("file")
    mc_kobo_id = new_id("masterclip")
    kobo_name = Path(clip.video_path).name

    # ── 口播 Video clipitem ──
    kobo_file_xml = build_file_xml(
        file_kobo_id, clip.video_path,
        v_w, v_h, v_tb, v_ntsc, v_dur,
        audio_depth=16, audio_sr=44100
    )

    kobo_video_clipitem = f"""                    <clipitem id="{ci_video_id}">
                        <masterclipid>{mc_kobo_id}</masterclipid>
                        <name>{kobo_name}</name>
                        <enabled>TRUE</enabled>
                        <duration>{v_dur}</duration>
                        <rate>
                            <timebase>{fps}</timebase>
                            <ntsc>FALSE</ntsc>
                        </rate>
                        <start>0</start>
                        <end>{v_dur}</end>
                        <in>0</in>
                        <out>{v_dur}</out>
                        <pproTicksIn>0</pproTicksIn>
                        <pproTicksOut>{frames_to_ticks(v_dur)}</pproTicksOut>
                        <alphatype>none</alphatype>
                        <pixelaspectratio>square</pixelaspectratio>
                        <anamorphic>FALSE</anamorphic>
{kobo_file_xml}
                        <link>
                            <linkclipref>{ci_video_id}</linkclipref>
                            <mediatype>video</mediatype>
                            <trackindex>1</trackindex>
                            <clipindex>1</clipindex>
                        </link>
                        <link>
                            <linkclipref>{ci_audio1_id}</linkclipref>
                            <mediatype>audio</mediatype>
                            <trackindex>1</trackindex>
                            <clipindex>1</clipindex>
                            <groupindex>1</groupindex>
                        </link>
                        <link>
                            <linkclipref>{ci_audio2_id}</linkclipref>
                            <mediatype>audio</mediatype>
                            <trackindex>2</trackindex>
                            <clipindex>1</clipindex>
                            <groupindex>1</groupindex>
                        </link>
{LOGGING_INFO}
                        <labels>
                            <label2>Iris</label2>
                        </labels>
                    </clipitem>"""

    # ── B-roll 匹配 ──
    matched = match_keywords(entries, rules, footage_map)

    broll_clipitems = []
    # 记录文件ID缓存，避免重复定义file节点
    file_id_cache: Dict[str, str] = {}

    for (entry, keyword, footage_path) in matched:
        # 获取素材信息
        f_w, f_h, f_tb, f_ntsc, f_dur_native = get_video_info(footage_path)

        # 素材时长（用序列fps换算）
        if f_dur_native:
            footage_dur_sec = f_dur_native / f_tb
        else:
            footage_dur_sec = 5.0  # 无法读取时默认5秒

        # 跳过 < 1秒素材
        if footage_dur_sec < 1.0:
            continue

        result = calc_broll_in_out(entry.duration_sec, footage_dur_sec, f_tb)
        if result is None:
            continue
        in_native, out_native = result

        # 在序列时间轴上的位置（以序列fps计算）
        seq_start = sec_to_frames(entry.start_sec, fps)
        # 素材在序列上占用的帧数（不超过口播句时长）
        clip_dur_sec = min(footage_dur_sec, entry.duration_sec)
        seq_end = sec_to_frames(entry.start_sec + clip_dur_sec, fps)

        # 如果素材 < 75%，从尾部对齐
        ratio = footage_dur_sec / entry.duration_sec if entry.duration_sec > 0 else 1
        if ratio < 0.75:
            seq_end = sec_to_frames(entry.end_sec, fps)
            seq_start = sec_to_frames(entry.end_sec - footage_dur_sec, fps)
            seq_start = max(0, seq_start)

        ci_broll_id = new_id("clipitem")
        mc_broll_id = new_id("masterclip")
        footage_name = Path(footage_path).name

        # file节点：同路径复用ID（引用方式）
        if footage_path in file_id_cache:
            f_id = file_id_cache[footage_path]
            file_xml = f'                        <file id="{f_id}"/>'
        else:
            f_id = new_id("file")
            file_id_cache[footage_path] = f_id
            file_xml = build_file_xml(
                f_id, footage_path,
                f_w, f_h, f_tb, f_ntsc,
                f_dur_native if f_dur_native else 0,
                audio_depth=16, audio_sr=48000,
                indent="                        "
            )

        broll_ci = f"""                    <clipitem id="{ci_broll_id}">
                        <masterclipid>{mc_broll_id}</masterclipid>
                        <name>{footage_name}</name>
                        <enabled>TRUE</enabled>
                        <duration>{f_dur_native if f_dur_native else 0}</duration>
                        <rate>
                            <timebase>{f_tb}</timebase>
                            <ntsc>{"TRUE" if f_ntsc else "FALSE"}</ntsc>
                        </rate>
                        <start>{seq_start}</start>
                        <end>{seq_end}</end>
                        <in>{in_native}</in>
                        <out>{out_native}</out>
                        <pproTicksIn>{frames_to_ticks(in_native)}</pproTicksIn>
                        <pproTicksOut>{frames_to_ticks(out_native)}</pproTicksOut>
                        <alphatype>none</alphatype>
                        <pixelaspectratio>square</pixelaspectratio>
                        <anamorphic>FALSE</anamorphic>
{file_xml}
{LOGGING_INFO}
                        <labels>
                            <label2>Iris</label2>
                        </labels>
                    </clipitem>"""
        broll_clipitems.append(broll_ci)

    broll_track_content = '\n'.join(broll_clipitems)

    # ── 口播音频 clipitem ──
    def audio_clipitem(ci_id, ch_idx, track_idx, output_ch):
        return f"""                    <clipitem id="{ci_id}" premiereChannelType="stereo">
                        <masterclipid>{mc_kobo_id}</masterclipid>
                        <name>{kobo_name}</name>
                        <enabled>TRUE</enabled>
                        <duration>{v_dur}</duration>
                        <rate>
                            <timebase>{fps}</timebase>
                            <ntsc>FALSE</ntsc>
                        </rate>
                        <start>0</start>
                        <end>{v_dur}</end>
                        <in>0</in>
                        <out>{v_dur}</out>
                        <pproTicksIn>0</pproTicksIn>
                        <pproTicksOut>{frames_to_ticks(v_dur)}</pproTicksOut>
                        <file id="{file_kobo_id}"/>
                        <sourcetrack>
                            <mediatype>audio</mediatype>
                            <trackindex>{ch_idx}</trackindex>
                        </sourcetrack>
                        <link>
                            <linkclipref>{ci_video_id}</linkclipref>
                            <mediatype>video</mediatype>
                            <trackindex>1</trackindex>
                            <clipindex>1</clipindex>
                        </link>
                        <link>
                            <linkclipref>{ci_audio1_id}</linkclipref>
                            <mediatype>audio</mediatype>
                            <trackindex>1</trackindex>
                            <clipindex>1</clipindex>
                            <groupindex>1</groupindex>
                        </link>
                        <link>
                            <linkclipref>{ci_audio2_id}</linkclipref>
                            <mediatype>audio</mediatype>
                            <trackindex>2</trackindex>
                            <clipindex>1</clipindex>
                            <groupindex>1</groupindex>
                        </link>
{LOGGING_INFO}
                        <labels>
                            <label2>Iris</label2>
                        </labels>
                    </clipitem>"""

    audio1_xml = audio_clipitem(ci_audio1_id, 1, 1, 1)
    audio2_xml = audio_clipitem(ci_audio2_id, 2, 2, 2)

    def empty_audio_track(ch_idx, out_ch):
        attrs = AUDIO_TRACK_ATTRS.format(idx=ch_idx - 1)
        return f"""            <track {attrs}>
                <enabled>TRUE</enabled>
                <locked>FALSE</locked>
                <outputchannelindex>{out_ch}</outputchannelindex>
            </track>"""

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="4">
    <sequence id="{seq_id}" {seq_attr}>
        <uuid>{seq_uuid}</uuid>
        <duration>{v_dur}</duration>
        <rate>
            <timebase>{fps}</timebase>
            <ntsc>FALSE</ntsc>
        </rate>
        <name>{clip.name}</name>
        <media>
            <video>
{seq_format_xml()}
                <track TL.SQTrackShy="0" TL.SQTrackExpandedHeight="41" TL.SQTrackExpanded="0" MZ.TrackTargeted="1">
{kobo_video_clipitem}
                    <enabled>TRUE</enabled>
                    <locked>FALSE</locked>
                </track>
                <track TL.SQTrackShy="0" TL.SQTrackExpandedHeight="41" TL.SQTrackExpanded="0" MZ.TrackTargeted="0">
{broll_track_content}
                    <enabled>TRUE</enabled>
                    <locked>FALSE</locked>
                </track>
            </video>
            <audio>
                <numOutputChannels>2</numOutputChannels>
                <format>
                    <samplecharacteristics>
                        <depth>16</depth>
                        <samplerate>44100</samplerate>
                    </samplecharacteristics>
                </format>
                <outputs>
                    <group>
                        <index>1</index>
                        <numchannels>1</numchannels>
                        <downmix>0</downmix>
                        <channel><index>1</index></channel>
                    </group>
                    <group>
                        <index>2</index>
                        <numchannels>1</numchannels>
                        <downmix>0</downmix>
                        <channel><index>2</index></channel>
                    </group>
                </outputs>
                <track {AUDIO_TRACK_ATTRS.format(idx=0)}>
{audio1_xml}
                    <enabled>TRUE</enabled>
                    <locked>FALSE</locked>
                    <outputchannelindex>1</outputchannelindex>
                </track>
                <track {AUDIO_TRACK_ATTRS.format(idx=1)}>
{audio2_xml}
                    <enabled>TRUE</enabled>
                    <locked>FALSE</locked>
                    <outputchannelindex>2</outputchannelindex>
                </track>
                <track {AUDIO_TRACK_ATTRS.format(idx=0)}>
                    <enabled>TRUE</enabled>
                    <locked>FALSE</locked>
                    <outputchannelindex>1</outputchannelindex>
                </track>
                <track {AUDIO_TRACK_ATTRS.format(idx=1)}>
                    <enabled>TRUE</enabled>
                    <locked>FALSE</locked>
                    <outputchannelindex>2</outputchannelindex>
                </track>
            </audio>
        </media>
        <timecode>
            <rate>
                <timebase>{fps}</timebase>
                <ntsc>FALSE</ntsc>
            </rate>
            <string>00:00:00:00</string>
            <frame>0</frame>
            <displayformat>NDF</displayformat>
        </timecode>
        <labels>
            <label2>Forest</label2>
        </labels>
        <logginginfo>
            <description></description>
            <scene></scene>
            <shottake></shottake>
            <lognote></lognote>
            <good></good>
            <originalvideofilename></originalvideofilename>
            <originalaudiofilename></originalaudiofilename>
        </logginginfo>
    </sequence>
</xmeml>"""

    return xml


# ─────────────────────────────────────────────
# 工程配置 保存 / 加载
# ─────────────────────────────────────────────

def get_projects_dir() -> Path:
    """工程文件存储目录，在程序所在目录的 projects/ 下"""
    # 在运行时取 sys.executable 或 __file__ 所在目录
    import sys
    base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    d = base / "projects"
    d.mkdir(exist_ok=True)
    return d


def save_project(config: ProjectConfig):
    d = get_projects_dir()
    path = d / f"{config.name}.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(config.__dict__, f, ensure_ascii=False, indent=2)


def load_project(name: str) -> Optional[ProjectConfig]:
    d = get_projects_dir()
    path = d / f"{name}.json"
    if not path.exists():
        return None
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    cfg = ProjectConfig()
    cfg.__dict__.update(data)
    return cfg


def list_projects() -> List[str]:
    d = get_projects_dir()
    return [p.stem for p in sorted(d.glob("*.json"))]


def delete_project(name: str):
    d = get_projects_dir()
    path = d / f"{name}.json"
    if path.exists():
        path.unlink()
