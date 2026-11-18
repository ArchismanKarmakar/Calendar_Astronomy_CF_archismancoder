// Site settings. Edit, commit, push — no build step needed.
window.SITE_CONFIG = {
  // Python in the browser. The public CDN is fine; to self-host, copy a Pyodide
  // 0.27.7 "full" release into site/pyodide/ and set this to "/pyodide/".
  pyodide: "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/",

  // Donations. Anything left empty is hidden. Fill in only what you actually use.
  donate: {
    upi: {
      id: "",                    // your UPI ID, e.g. "yourname@okhdfcbank"
      name: "Archisman Karmakar", // name shown in the payer's UPI app
      note: "Deep Space Explorer 2027 calendar",
      amounts: [99, 199, 499],   // suggested amounts in INR
    },
    kofi: "",                    // e.g. "https://ko-fi.com/yourname"
    buymeacoffee: "",            // e.g. "https://buymeacoffee.com/yourname"
    paypal: "",                  // e.g. "https://paypal.me/yourname"
    github_sponsors: "",         // e.g. "https://github.com/sponsors/ArchismanKarmakar"
    other: [],                   // e.g. [{ label: "Razorpay", url: "https://rzp.io/l/..." }]
  },

  // Shown in the footer and on the Terms page.
  author: { name: "ArchismanCoder", url: "https://archismancoder.com" },
  contact_email: "",           // optional, e.g. "hello@archismancoder.com" (used on the Terms page)
};
