#!/usr/bin/env python3
# coding: utf8

from pathlib import Path
from json import loads
from subprocess import run, CalledProcessError, PIPE
from . import Utils
from .BaseMedia import BaseMedia
from typing import Dict, List, Union, Any, Optional
from datetime import datetime
import piexif
import magic
import re

JSONValue = Union[str, int, float, bool, None, Dict[str, Any], List[Any]]
JSONType = Union[Dict[str, JSONValue], List[JSONValue]]

# command to extract creation date from video files
FF_PROBE = [
    "ffprobe", "-v", "quiet", "-print_format", "json", "-show_entries",
    "stream=index,codec_type:stream_tags=creation_time:format_"
    "tags=creation_time"
]

# Huawei adds these camera modes to description but Google Photos seems wise to
# it and does not report this in its description metadata
# noinspection SpellCheckingInspection
HUAWEI_JUNK = ['jhdr', 'edf', 'sdr', 'cof', 'nor', 'mde', 'oznor', 'btf',
               'btfmdn', 'ptfbty', 'mef', 'bsh', 'dav', 'rpt', 'fbt',
               'burst', 'rhdr', 'fbtmdn', 'ptr', 'rbtoz', 'btr', 'rbsh',
               'btroz']
# regex to check if this (might be) a duplicate with ' (n)' suffix. Note that
# 'demo (0).jpg' and 'demo (1).jpg' are not in the scheme
# but 'demo (2).jpg' to 'demo (999).jpg' are
DUPLICATE_MATCH = re.compile(r'(.*) \(([2-9]|\d{2,3})\)\.(.*)')


class LocalFilesMedia(BaseMedia):
    mime = magic.Magic(mime=True)

    def __init__(self, full_path: Path):
        super(LocalFilesMedia, self).__init__()
        self.__mime_type: str = self.mime.from_file(str(full_path))
        self.is_video: bool = self.__mime_type.startswith('video')
        self.__full_path: Path = full_path
        self.__original_name: Path = full_path.name
        self.__ffprobe_installed = True
        self.__createDate: datetime = None

        self.got_meta: bool = False
        self.__exif_0: dict = {}
        self.__exif: dict = {}

        matches = DUPLICATE_MATCH.match(str(full_path.name))
        if matches:
            # this is (probably) a duplicate with 'file (n).jpg' format
            # extract the original name and duplicate no.
            # -1 is because the first duplicate is labelled ' (2)'
            self.duplicate_number: int = int(matches[2]) - 1
            self.__original_name = matches[1] + '.' + matches[3]

        if self.is_video:
            self.get_video_meta()
        else:
            self.get_exif()
            self.get_image_date()

    def get_video_meta(self):
        if self.__ffprobe_installed:
            try:
                command = FF_PROBE + [str(self.__full_path)]
                result = run(command, stdout=PIPE, check=True)
                out = str(result.stdout.decode("utf-8"))
                json = loads(out)
                t = json["format"]["tags"]["creation_time"]
                self.__createDate = Utils.string_to_date(t)
                self.got_meta = True
            except FileNotFoundError:
                # this means there is no ffprobe installed
                self.__ffprobe_installed = False
            except CalledProcessError:
                pass
            except KeyError:
                # ffprobe worked but there is no creation time in the JSON
                pass

        if not self.__createDate:
            # just use file date
            self.__createDate = datetime.utcfromtimestamp(
                self.__full_path.stat().st_mtime)

    def get_image_date(self):
        photo_date = None
        if self.got_meta:
            try:
                d_bytes = self.__exif.get(piexif.ExifIFD.DateTimeOriginal)
                photo_date = Utils.string_to_date(d_bytes.decode("utf-8"))
            except (KeyError, ValueError, AttributeError):
                try:
                    d_bytes = self.__exif_0.get(piexif.ImageIFD.DateTime)
                    photo_date = Utils.string_to_date(d_bytes.decode("utf-8"))
                except (KeyError, ValueError, AttributeError):
                    pass

        if not photo_date:
            # just use file date
            photo_date = datetime.utcfromtimestamp(
                self.__full_path.stat().st_mtime)
        self.__createDate = photo_date

    def get_exif(self):
        try:
            exif = piexif.load(str(self.__full_path))
            self.got_meta = True
            self.__exif_0: dict = exif["0th"]
            self.__exif: dict = exif["Exif"]
        except piexif.InvalidImageDataError:
            self.got_meta = False

    @property
    def uid(self) -> str:
        if self.got_meta and self.is_video:
            uid = 'not_supported'
        else:
            uid = self.__exif.get(piexif.ExifIFD.ImageUniqueID)
        return uid

    # ----- override Properties below -----
    @property
    def relative_folder(self) -> Path:
        return self.__full_path.parent

    @property
    def size(self) -> int:
        return self.__full_path.stat().st_size

    @property
    def id(self) -> Optional[str]:
        return None

    @property
    def description(self) -> str:
        d = self.__exif_0.get(piexif.ImageIFD.ImageDescription)
        if d:
            result = d.decode("utf-8")
            if result in HUAWEI_JUNK:
                result = ''
        else:
            result = ''
        return result

    @property
    def orig_name(self) -> str:
        return self.__original_name

    @property
    def create_date(self) -> datetime:
        return self.__createDate

    @property
    def modify_date(self) -> datetime:
        return self.create_date

    @property
    def mime_type(self) -> str:
        return self.__mime_type

    @property
    def url(self) -> Optional[str]:
        return None

    @property
    def camera_model(self):
        return self.__exif_0.get(piexif.ImageIFD.CameraSerialNumber)
