"""Tar with zstd level 3; raw tar is used only inside workbench archives."""
from contextlib import ExitStack
from io import BytesIO
from types import SimpleNamespace
import tarfile
import tempfile

import zstandard


class Archive:
    def __init__(self, path, mode='r', *_, compressed=True):
        self.stack = ExitStack()
        try:
            self.output = mode == 'w'
            raw = self.stack.enter_context(open(path, 'wb' if self.output else 'rb'))
            if self.output:
                writer = self.stack.enter_context(zstandard.ZstdCompressor(level=3, write_checksum=True).stream_writer(raw, closefd=False)) if compressed else raw
                self.tar = self.stack.enter_context(tarfile.open(fileobj=writer, mode='w|', format=tarfile.PAX_FORMAT))
            else:
                raw.seek(0)
                magic = raw.read(4)
                raw.seek(0)
                temporary = raw
                if magic == b'\x28\xb5\x2f\xfd':
                    temporary = self.stack.enter_context(tempfile.TemporaryFile())
                    with zstandard.ZstdDecompressor(max_window_size=128*1024*1024).stream_reader(raw, closefd=False) as reader:
                        size = 0
                        while chunk := reader.read(1024*1024):
                            size += len(chunk)
                            if size > 3*1024**3:
                                raise ValueError('备份解压后超过大小限制')
                            temporary.write(chunk)
                    temporary.seek(0)
                self.tar = self.stack.enter_context(tarfile.open(fileobj=temporary, mode='r:'))
                self.members = []
                size = 0
                for member in self.tar:
                    size += member.size
                    if size > 3*1024**3:
                        raise ValueError('备份解压后超过大小限制')
                    if not member.isfile() or len(self.members) >= 50000:
                        raise ValueError('备份包含特殊文件或文件数量过多')
                    self.members.append(member)
        except (tarfile.TarError, zstandard.ZstdError) as exc:
            self.stack.close()
            raise ValueError('备份格式无效，仅支持当前 tar.zst 归档') from exc
        except BaseException:
            self.stack.close()
            raise

    def namelist(self):
        return [m.name for m in self.members]

    def infolist(self):
        return [SimpleNamespace(file_size=m.size) for m in self.members]

    def read(self, name):
        member = next((m for m in self.members if m.name == name), None)
        if member is None:
            raise ValueError('备份缺少文件：' + name)
        with self.tar.extractfile(member) as source:
            return source.read()

    def writestr(self, name, raw):
        if isinstance(raw, str):
            raw = raw.encode('utf-8')
        member = tarfile.TarInfo(name)
        member.size = len(raw)
        member.mode = 0o600
        self.tar.addfile(member, BytesIO(raw))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return self.stack.__exit__(*args)
