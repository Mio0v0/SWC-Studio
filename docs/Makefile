# Minimal Sphinx Makefile

SPHINXBUILD ?= sphinx-build
SOURCEDIR   = .
BUILDDIR    = _build

.PHONY: help html clean

help:
	@LC_ALL=C $(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)"

html:
	@LC_ALL=C $(SPHINXBUILD) -b html "$(SOURCEDIR)" "$(BUILDDIR)/html"
	@rm -rf "$(BUILDDIR)/html/_sources"

clean:
	rm -rf "$(BUILDDIR)"
