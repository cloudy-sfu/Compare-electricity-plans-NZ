function open_new_tab_html(text) {
    let newTab = window.open();
    if (newTab) {
        newTab.document.write(text);
        newTab.document.close(); // Ensure the document is fully loaded
    } else {
        console.error("Popup blocked. Allow popups to open new tabs.");
    }
}
