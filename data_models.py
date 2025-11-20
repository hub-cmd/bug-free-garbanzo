class RevisionEntry:
    """
    Data model class to represent a single parsed entry (Activity or Comment)
    from the Airtable revision history.
    """
    def __init__(self, data):
        # Mandatory fields for all entries
        self.id = data.get("id")
        self.type = data.get("type")
        self.timestamp = data.get("createdTime")
        user = data.get("user", {})
        self.user = {
            "id": user.get("id"),
            "email": user.get("email"),
            "name": user.get("name")
        }

        # Comment-specific field
        self.comment = data.get("comment")

        # Activity-specific fields
        self.columnId = data.get("columnId")
        self.columnName = data.get("columnName")
        self.columnType = data.get("columnType")
        self.oldValue = data.get("oldValue")
        self.newValue = data.get("newValue")

    def to_dict(self):
        """Returns a clean dictionary representation for JSON serialization."""
        data = {
        "id": self.id,
        "type": self.type,
        "user": self.user,
        "timestamp": self.timestamp,
        }
        # Conditionally add fields based on type for a cleaner output
        if self.type == "comment":
            data["comment"] = self.comment
        else: # Activity
            data.update({
                "columnId": self.columnId,
                "columnName": self.columnName,
                "columnType": self.columnType,
                "oldValue": self.oldValue,
                "newValue": self.newValue,
        })
        return data