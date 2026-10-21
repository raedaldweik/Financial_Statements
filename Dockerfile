# Investor Financial Intelligence demo — static site served by nginx.
# Railway injects $PORT; the official nginx image renders the config template
# from /etc/nginx/templates/ with envsubst at start-up.
FROM nginx:1.27-alpine

ENV PORT=8080
EXPOSE 8080

COPY deploy/default.conf.template /etc/nginx/templates/default.conf.template

# the app: pages, assets, generated data bundles and the source filings (deep-linked by page)
COPY index.html portfolio.html company.html /usr/share/nginx/html/
COPY assets/   /usr/share/nginx/html/assets/
COPY data/     /usr/share/nginx/html/data/
COPY filings/  /usr/share/nginx/html/filings/
