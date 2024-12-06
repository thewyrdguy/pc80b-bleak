import gi
import cairo

gi.require_version("GLib", "2.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst, Gtk

CAPS = (
    "video/x-raw,format=RGBA,bpp=32,depth=32,width=1080,height=720"
    ",red_mask=-16777216,green_mask=16711680,blue_mask=65280"
    ",alpha_mask=255,endianness=4321,framerate=1/30"
)

class GUI:
    def __init__(self, app: Gtk.Application) -> None:
        self.app = app
        self.counter = 0

        self.pipeline = Gst.Pipeline.new()
        bus = self.pipeline.get_bus()
        bus.connect("message::eos", self.on_eos)
        bus.connect("message::error", self.on_error)

        gtksink = Gst.ElementFactory.make('gtk4paintablesink', None)
        paintable = gtksink.get_property('paintable')
        if not paintable.props.gl_context:
            raise RuntimeError("Refusing to run without OpenGL")
        sink = Gst.ElementFactory.make('glsinkbin', None)
        sink.set_property('sink', gtksink)

        src = Gst.ElementFactory.make('appsrc', None)
        src.set_property("format", Gst.Format.TIME)

        self.pipeline.add(src)
        self.pipeline.add(sink)

        src.link_filtered(sink, Gst.Caps.from_string(CAPS))

        src.connect("need-data", self.on_need_data)

        self.window = Gtk.ApplicationWindow(application=app)
        self.window.set_default_size(1080, 720)
        self.window.set_title("pc80b-ble")

        picture = Gtk.Picture.new()
        picture.set_paintable(paintable)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.append(picture)
        label = Gtk.Label.new("Bottom Label")
        vbox.append(label)

        self.window.set_child(vbox)
        self.window.present()

        app.add_window(self.window)

        app.connect('shutdown', self.on_close)

        self.pipeline.set_state(Gst.State.PLAYING)

    def on_close(self, _):
        self.window.close()
        self.pipeline.set_state(Gst.State.NULL)

    def on_eos(self, bus, msg):
        print("End of stream")
        self.app.quit()

    def on_error(self, bus, msg):
        error = msg.parse_error()
        print("ERROR", error)

    def on_need_data(self, source, amount):
        with cairo.ImageSurface(cairo.FORMAT_ARGB32, 1080, 720) as image:
            context = cairo.Context(image)
            context.set_source_rgba(0.5, 0.0, 0.0, 1.0)
            context.rectangle(0, 0, 1080, 720)
            context.fill()
            context.select_font_face(
                "sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD
            )
            context.set_font_size(48)
            text = "Hello World!  " + str(self.counter)
            (x, y, w, h, dx, dy) = context.text_extents(text)
            context.move_to((1080 - w) / 2.0, (720 - h) / 2.0)
            context.set_source_rgba(1.0, 1.0, 1.0, 1.0)
            context.show_text(text)
            # Gst.Buffer.add_reference_timestamp_meta(
            #   self, reference, timestamp, duration
            # )
            # timestamp/x-unix: for timestamps based on the UNIX epoch
            source.emit(
                "push-buffer",
                Gst.Buffer.new_wrapped_bytes(GLib.Bytes.new(image.get_data())),
            )

    def push_data(self, i):
        self.counter = i


if __name__ == "__main__":
    Gst.init()
    Gtk.init()
    app = Gtk.Application()
    app.connect('activate', GUI)
    try:
        res = app.run()
        print("exit", res)
    except KeyboardInterrupt:
        app.quit()
