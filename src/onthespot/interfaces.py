from .constants import ItemStatus


class Item:
    def __init__(self):
        # internal data
        self.local_id = ""
        self.available = False
        self.item_status: ItemStatus = ItemStatus.WAITING
        self.path = ""
        # parsing info
        self.item_url = ""
        self.item_service = ""
        self.item_type = ""
        self.item_id = ""
        # only collections
        self.playlist_name = ""
        self.playlist_by = ""
        self.parent_category = ""
        self.playlist_numeber = ""
        # metadata store
        self.item_metadata = {}
