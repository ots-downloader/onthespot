import os
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QWidget
from ..runtimedata import download_queue, get_logger
from ..utils import open_item

logger = get_logger("worker.utility")


class DownloadActionsButtons(QWidget):
    def __init__(
        self,
        local_id,
        item_metadata,
        pbar,
        copy_btn,
        cancel_btn,
        retry_btn,
        open_btn,
        locate_btn,
        delete_btn,
        parent=None,
    ):
        super(DownloadActionsButtons, self).__init__(parent)
        self.local_id = local_id
        self.item_metadata = item_metadata
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(pbar)
        if copy_btn is not None:
            self.copy_btn = copy_btn
            copy_btn.clicked.connect(self.copy_link)
            layout.addWidget(copy_btn)
        self.cancel_btn = cancel_btn
        cancel_btn.clicked.connect(self.cancel_item)
        layout.addWidget(cancel_btn)
        self.retry_btn = retry_btn
        retry_btn.clicked.connect(self.retry_item)
        layout.addWidget(retry_btn)
        if open_btn is not None:
            self.open_btn = open_btn
            open_btn.clicked.connect(self.open_file)
            layout.addWidget(open_btn)
        if locate_btn is not None:
            self.locate_btn = locate_btn
            locate_btn.clicked.connect(self.locate_file)
            layout.addWidget(locate_btn)
        if delete_btn is not None:
            self.delete_btn = delete_btn
            delete_btn.clicked.connect(self.delete_file)
            layout.addWidget(delete_btn)
        self.setLayout(layout)

    def copy_link(self):
        QApplication.clipboard().setText(self.item_metadata["item_url"])

    def cancel_item(self):
        download_queue[self.local_id]["item_status"] = "Cancelled"
        download_queue[self.local_id]["gui"]["status_label"].setText(
            self.tr("Cancelled")
        )
        download_queue[self.local_id]["gui"]["progress_bar"].setValue(0)
        self.cancel_btn.hide()
        self.retry_btn.show()

    def retry_item(self):
        download_queue[self.local_id]["item_status"] = "Waiting"
        download_queue[self.local_id]["gui"]["status_label"].setText(self.tr("Waiting"))
        download_queue[self.local_id]["gui"]["progress_bar"].setValue(0)
        self.retry_btn.hide()
        self.cancel_btn.show()

    def open_file(self):
        file_path = download_queue[self.local_id]["file_path"]
        file = os.path.abspath(file_path)
        open_item(file)

    def locate_file(self):
        file_path = download_queue[self.local_id]["file_path"]
        file_dir = os.path.dirname(file_path)
        open_item(file_dir)

    def delete_file(self):
        file_path = download_queue[self.local_id]["file_path"]
        file = os.path.abspath(file_path)
        os.remove(file)
        download_queue[self.local_id]["item_status"] = "Deleted"
        download_queue[self.local_id]["gui"]["status_label"].setText(self.tr("Deleted"))
        self.open_btn.hide()
        self.locate_btn.hide()
        self.delete_btn.hide()
        self.retry_btn.show()
