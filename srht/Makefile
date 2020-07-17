# Run `make` to compile static assets
# Run `make watch` to recompile whenever a change is made

.PHONY: all static watch clean

SRHT_PATH?=/usr/lib/python3.8/site-packages/srht

_STATIC:=$(patsubst _static/%,$(MODULE)static/%,$(wildcard _static/*.*))
_STATIC+=$(patsubst $(SRHT_PATH)/static/%,$(MODULE)static/%,$(wildcard $(SRHT_PATH)/static/*.*))
_STATIC+=$(patsubst $(SRHT_PATH)/static/%,$(MODULE)static/%,$(wildcard $(SRHT_PATH)/static/icons/*))

$(MODULE)static/%: $(SRHT_PATH)/static/%
	@mkdir -p $(MODULE)static/
	cp -L $< $@

$(MODULE)static/%: _static/%
	@mkdir -p $(MODULE)static/
	cp -RLf $< $@

$(MODULE)static/icons/%: $(SRHT_PATH)/static/icons/%
	@mkdir -p $(MODULE)static/icons/
	cp -L $< $@

$(MODULE)static/main.css: scss/*.scss ${SRHT_PATH}/scss/*.scss
	@mkdir -p $(MODULE)static/
	sassc -I${SRHT_PATH}/scss scss/main.scss $@

$(MODULE)static/main.min.css: $(MODULE)static/main.css
	node ${SRHT_PATH}/node_modules/clean-css-cli/bin/cleancss \
		-o static/main.min.css \
		static/main.css
	cp static/main.min.css \
		static/main.min.$$(sha256sum static/main.min.css | cut -c1-8).css

$(MODULE)static/%.js: js/%.js
	@mkdir -p $(MODULE)static/
	cp $< $@

static: $(_STATIC) $(MODULE)static/main.min.css

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
