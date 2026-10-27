// Harmless look-alikes: none of these should be reported.
const cors = require("cors");
app.use(cors({ origin: "https://www.example-client.com" }));
app.use(session({ cookie: { secure: true, httpOnly: true } }));
const DEBUG = false;
