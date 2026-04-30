class BlenderManagerError(Exception):
    pass

class ConfigError(BlenderManagerError):
    pass

class FileReadError(BlenderManagerError):
    def __init__(self, file_path, message=None):
        self.file_path = file_path
        self.message = message or f"Failed to read file: {file_path}"
        super().__init__(self.message)

class FileWriteError(BlenderManagerError):
    def __init__(self, file_path, message=None):
        self.file_path = file_path
        self.message = message or f"Failed to write file: {file_path}"
        super().__init__(self.message)

class NetworkError(BlenderManagerError):
    def __init__(self, url=None, message=None):
        self.url = url
        self.message = message or "Network operation failed"
        super().__init__(self.message)

class VersionError(BlenderManagerError):
    pass

class ThreadError(BlenderManagerError):
    pass

class PlatformError(BlenderManagerError):
    pass

class ValidationError(BlenderManagerError):
    pass
