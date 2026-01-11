class Member:
    def __init__(self, uuid, name, level, rank, original_join_date, last_join_date, power=0):
        self.uuid = uuid
        self.name = name
        self.level = level
        self.rank = rank
        self.original_join_date = original_join_date
        self.last_join_date = last_join_date
        self.power = power
        self.previous_names = []
        self.service_events = []

    def to_json(self):
        return {
            "uuid": self.uuid,
            "name": self.name,
            "level": self.level,
            "rank": self.rank,
            "original_join_date": self.original_join_date,
            "last_join_date": self.last_join_date,
            "power": self.power,
            "previous_names": self.previous_names,
            "events": self.service_events,
        }

    @staticmethod
    def from_json(data):
        m = Member(
            data["uuid"],
            data["name"],
            data["level"],
            data["rank"],
            data.get("original_join_date"),
            data.get("last_join_date"),
            data.get("power", 0),
        )
        m.previous_names = data.get("previous_names", [])
        m.service_events = data.get("events", [])
        return m
