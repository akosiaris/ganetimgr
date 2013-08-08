Copyright © 2010-2012 Greek Research and Technology Network (GRNET S.A.)

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND ISC DISCLAIMS ALL WARRANTIES WITH REGARD
TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS. IN NO EVENT SHALL ISC BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR
CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE,
DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS
ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS
SOFTWARE.


To setup an instance:

manage.py syncdb (*** Do not create superuser yet ***)
manage.py migrate
manage.py createsuperuser

Migrating to v1.0:
-install python-ipaddr lib
-update settings.py and urls.py with latest changes from dist files
Run:
manage.py migrate

If your web server is nginx, consider placing:

proxy_set_header X-Forwarded-Host <hostname>;
in your nginx site location part
and
USE_X_FORWARDED_HOST = True
in your settings.py. 
The above ensure that i18n operates properly when switching between languages. 

Migrating to v1.2
- Make sure to:
	- Set the RAPI_TIMEOUT in settings.py (see .dist)
	- Set the NODATA_IMAGE path in settings.py.dist
	- Update urls.py to urls.py.dist
