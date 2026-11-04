"""SQLite row mapping and explicit connection ownership."""
import sqlite3


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect(path, *, close_on_exit=False, **options):
    factory = ClosingConnection if close_on_exit else sqlite3.Connection
    db = sqlite3.connect(path, factory=factory, **options)
    db.row_factory = sqlite3.Row
    return db
