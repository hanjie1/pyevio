"""Main application class for the pyevio UI."""
import os
from rich.text import Text
from textual.app import App
from textual.widgets import Header, Footer, Tree, RichLog
from textual.containers import Container, Horizontal
from textual.binding import Binding

class PyEvioApp(App):
    """The main pyevio UI application."""

    BINDINGS = [
        Binding(key="f2", action="view", description="View"),
        Binding(key="f10", action="exit", description="Exit"),
    ]

    CSS = """
    #main-container {
        height: 100%;
    }
    
    #left-panel {
        width: 30%;
        min-width: 20;
        border: solid $accent;
    }
    
    #right-panel {
        width: 70%;
        min-width: 50;
        background: $surface;
        border: solid $accent;
        overflow-y: auto;
    }
    
    Tree {
        padding: 1;
    }
    
    RichLog {
        padding: 1;
    }
    """

    def __init__(self, file_path: str):
        """Initialize the application with a file path."""
        super().__init__()
        self.file_path = file_path
        self.file_size = 0  # Will be set during setup

    def compose(self):
        """Compose the UI layout."""
        # Calculate file size
        try:
            self.file_size = os.path.getsize(self.file_path)
            # Create the title
            title = f"{self.file_path} ({self.file_size/1024:.2f} KB)"
        except OSError as e:
            title = f"{self.file_path} (Error: {str(e)})"

        yield Header(title)

        with Horizontal(id="main-container"):
            # Left panel with tree
            tree = Tree("File Structure", id="file-tree")
            tree.root.expand()

            # Yield the container first
            left_panel = Container(tree, id="left-panel")
            yield left_panel

            # Right panel with text (using RichLog for better scrolling)
            right_log = RichLog(id="detail-view")
            right_log.write("Select an item in the tree to view details.")
            yield Container(right_log, id="right-panel")

        yield Footer()

    def on_mount(self):
        """Called when the app is mounted."""
        self.build_tree()

    def build_tree(self):
        """Build the initial file structure tree with sample data."""
        # Get the tree widget
        tree = self.query_one("#file-tree", Tree)

        # Add the file header
        file_node = tree.root.add("File Header")
        file_node.add("Magic Number: EVIO")
        file_node.add("Version: 6")
        file_node.add("Endianness: Little Endian")

        # Add records
        records_node = tree.root.add("Records")
        # Add sample data for now
        for i in range(5):
            record_node = records_node.add(f"Record #{i}")
            record_node.add(f"Length: {100 + i*10} words")
            record_node.add(f"Events: {i+1}")

            # Add sample events
            events_node = record_node.add("Events")
            for j in range(i+1):
                event_node = events_node.add(f"Event #{j}")
                event_node.add(f"Length: {50 + j*5} bytes")
                event_node.add(f"Type: Physics")

    def on_tree_node_highlighted(self, event):
        """Handle tree node highlighting."""
        # Update the right panel with information about the highlighted node
        node = event.node

        # Get the text view widget
        text_view = self.query_one("#detail-view", RichLog)

        # Clear previous content
        text_view.clear()

        if "File Header" in node.label:
            text_view.write("# File Header Information\n")
            text_view.write("\nMagic Number: EVIO (0x4556494F)")
            text_view.write("\nVersion: 6")
            text_view.write("\nEndianness: Little")
            text_view.write("\nRecord Count: 5")
            text_view.write("\nIndex Array Length: 0 bytes")
            text_view.write("\nUser Header Length: 0 bytes")
            text_view.write("\nTrailer Position: 0x0")

        elif "Record #" in node.label:
            record_num = node.label.split("#")[1]
            text_view.write(f"# Record {record_num} Information\n")
            text_view.write(f"\nOffset: 0x{1000 + int(record_num) * 100:X}")
            text_view.write(f"\nLength: {100 + int(record_num) * 10} words")
            text_view.write(f"\nEvents: {int(record_num) + 1}")
            text_view.write(f"\nType: Physics")
            text_view.write(f"\nCompression: None")

        elif node.label.plain.startswith("Event #"):
            event_num = node.label.split("#")[1]
            text_view.write(f"# Event {event_num} Information\n")
            text_view.write(f"\nOffset: 0x{2000 + int(event_num) * 50:X}")
            text_view.write(f"\nLength: {50 + int(event_num) * 5} bytes")
            text_view.write(f"\nType: Physics")
            text_view.write(f"\nBank Tag: 0xFF60")
            text_view.write(f"\nBank Type: 0x10")

        elif "Magic Number" in node.label:
            text_view.write("# Magic Number\n")
            text_view.write("\nThe magic number identifies this file as an EVIO file.")
            text_view.write("\nValue: 0x4556494F (ASCII: 'EVIO')")
            text_view.write("\nLocation: First word of file header")

        elif "Version" in node.label:
            text_view.write("# Version Information\n")
            text_view.write("\nThis file uses EVIO format version 6.")
            text_view.write("\nVersion 6 supports data compression and enhanced metadata.")

        elif "Endianness" in node.label:
            text_view.write("# Endianness\n")
            text_view.write("\nThis file uses little endian byte ordering.")
            text_view.write("\nThis means the least significant byte is stored first.")

        elif "Length" in node.label:
            text_view.write("# Length Information\n")
            length_val = node.label.split(": ")[1].split(" ")[0]
            text_view.write(f"\nThe length is {length_val} words/bytes.")
            text_view.write("\nFor records, length is measured in 32-bit words.")
            text_view.write("\nFor events, length is typically measured in bytes.")

        elif "Events" in node.label and ": " in node.label:
            text_view.write("# Event Count\n")
            count = node.label.split(": ")[1]
            text_view.write(f"\nThis record contains {count} events.")
            text_view.write("\nEach event contains a bank structure with data.")

        elif node.label == "Events":
            text_view.write("# Events\n")
            text_view.write("\nEvents contain the actual physics data.")
            text_view.write("\nEach event has a hierarchical bank structure.")
            text_view.write("\nSelect an event to see more details.")

        else:
            text_view.write(f"# {node.label}\n")
            text_view.write("\nNo detailed information available.")

    def action_view(self):
        """Handle the view action (F2)."""
        self.notify("Detail view mode - Press F10 to exit")

    def action_exit(self):
        """Handle the exit action (F10)."""
        self.exit()