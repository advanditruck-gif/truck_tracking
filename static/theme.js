(() => {
    const key = 'advandi-theme';
    const button = document.getElementById('theme-toggle');
    const metaTheme = document.querySelector('meta[name="theme-color"]');

    function applyTheme(theme, persist) {
        const selected = theme === 'light' ? 'light' : 'dark';
        document.documentElement.dataset.theme = selected;
        if (metaTheme) metaTheme.content = selected === 'light' ? '#f4f6fa' : '#080c16';
        if (button) {
            const next = selected === 'light' ? 'dark' : 'light';
            button.setAttribute('aria-label', 'Switch to ' + next + ' theme');
            button.setAttribute('aria-pressed', String(selected === 'light'));
            button.title = 'Switch to ' + next + ' theme';
        }
        if (persist) {
            try {
                localStorage.setItem(key, selected);
            } catch (error) {
                console.warn('Could not save theme preference:', error);
            }
        }
    }

    let savedTheme = 'dark';
    try {
        savedTheme = localStorage.getItem(key) || 'dark';
    } catch (error) {
        console.warn('Could not read theme preference:', error);
    }
    applyTheme(savedTheme, false);

    if (button) {
        button.addEventListener('click', () => {
            const next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
            applyTheme(next, true);
        });
    }

    window.addEventListener('storage', event => {
        if (event.key === key) applyTheme(event.newValue, false);
    });
})();
