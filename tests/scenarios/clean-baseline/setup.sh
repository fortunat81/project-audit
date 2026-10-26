# An ignored .env with harmless content: must not be flagged
printf 'API_URL=https://example.com\nLOG_LEVEL=info\n' > .env
