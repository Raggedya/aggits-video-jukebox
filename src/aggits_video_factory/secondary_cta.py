"""One optional project-level link, independent of primary CTA and analytics."""
import re
from urllib.parse import urlsplit


def normalize_cta2(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError('CTA 2 must contain a URL and button text.')
    url = str(value.get('url') or '').strip()
    if not url:
        return None
    try:
        parsed = urlsplit(url)
        valid = (parsed.scheme in {'http', 'https'} and parsed.hostname
                 and not parsed.username and not parsed.password and parsed.port != 0)
    except ValueError:
        valid = False
    if not valid or re.search(r'[\s\\\x00-\x1f\x7f]', url):
        raise ValueError('CTA 2 URL must be a complete, valid http or https URL.')
    label = re.sub(r'\s+', ' ', str(value.get('label') or '')).strip() or 'FIND OUT MORE'
    if len(label) > 80:
        raise ValueError('CTA 2 button text must be 80 characters or fewer.')
    if len(url) > 2048:
        raise ValueError('CTA 2 URL is too long (maximum 2048 characters).')
    return {'url': url, 'label': label}


def add_editor_fields(form, row, background, foreground):
    import tkinter as tk
    form.cta2_url_var = tk.StringVar(master=form)
    form.cta2_label_var = tk.StringVar(master=form)
    for key, label, variable in (
        ('cta2_url', 'CTA 2 URL (optional)', form.cta2_url_var),
        ('cta2_label', 'CTA 2 BUTTON TEXT', form.cta2_label_var),
    ):
        tk.Label(form, text=label, bg=background, fg=foreground, font=('Segoe UI', 9)).grid(
            row=row, column=0, sticky='e', padx=(22, 12), pady=4)
        entry = tk.Entry(form, textvariable=variable, bg='#0d0f13', fg=foreground,
                         insertbackground=foreground, font=('Segoe UI', 9))
        entry.grid(row=row, column=1, sticky='ew', padx=(0, 22), pady=4, ipady=4)
        form.field_widgets[key] = entry
        row += 1
    return row
