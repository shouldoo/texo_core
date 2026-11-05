# The coordination Odoo: the official image plus markdown2, without which the mail module
# logs a WARNING at every start (and checklog-odoo fails).
FROM odoo:20.0
USER root
RUN pip install --quiet --break-system-packages markdown2
USER odoo
