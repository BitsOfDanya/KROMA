class NotFoundError(LookupError):
    def __init__(self, entity: str, identifier: str) -> None:
        super().__init__(f"{entity} {identifier} not found")
        self.entity = entity
        self.identifier = identifier
