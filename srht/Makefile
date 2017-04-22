# Run `make` to compile static assets
# Run `make watch` to recompile whenever a change is made

.PHONY: all static watch clean

SCRIPTS+=$(patsubst js/%.js,$(MODULE)static/%.js,$(wildcard js/*.js))
_STATIC:=$(patsubst _static/%,$(MODULE)static/%,$(wildcard _static/*))

SRHT_PATH?=/usr/lib/python3.6/site-packages/srht

$(MODULE)static/%: _static/%
	@mkdir -p $(MODULE)static/
	cp -L $< $@

$(MODULE)static/main.css: scss/*.scss ${SRHT_PATH}/scss/*.scss
	@mkdir -p $(MODULE)static/
	sassc -I${SRHT_PATH}/scss scss/main.scss $@

$(MODULE)static/main.min.css: $(MODULE)static/main.css
	node ${SRHT_PATH}/minify-css.js \
		static/main.css \
		static/main.min.css \
		"$(MODULE)templates/*" "${SRHT_PATH}/templates/*"

$(MODULE)static/%.js: js/%.js
	@mkdir -p $(MODULE)static/
	cp $< $@

static: $(SCRIPTS) $(_STATIC) $(MODULE)static/main.min.css

all: static

clean:
	rm -rf $(MODULE)static

watch:
	while inotifywait \
		-e close_write js/ \
		-e close_write scss/ \
		-e close_write "${SRHT_PATH}"/scss/ \
		-e close_write $(MODULE)/templates/ \
		-e close_write _static/; \
		do make; done

.DEFAULT_GOAL=all
