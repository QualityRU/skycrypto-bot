class BadRequestError(Exception):
    def __init__(self, detail: str, status: int = 403):
        self.detail = detail
        self.status = status

    def __str__(self) -> str:
        return self.detail
