# Makefile for TLA+ verification artifacts
# "The Price of Safe Exploration in Flexible Paxos"

PYTHON = python3
TLA2TOOLS = tla2tools.jar  # download from https://github.com/tlaplus/tlaplus/releases

.PHONY: verify verify-extended dot latex clean tlc help

help:
	@echo "Targets:"
	@echo "  verify          Run Python verifier for N=3..10 (default)"
	@echo "  verify-extended Run Python verifier for N=3..15"
	@echo "  dot             Generate Graphviz DOT files"
	@echo "  latex           Generate LaTeX table"
	@echo "  tlc             Run TLC model checker (requires Java + tla2tools.jar)"
	@echo "  clean           Remove generated files"

verify:
	$(PYTHON) verify_all.py

verify-extended:
	$(PYTHON) verify_all.py --max-n 15

dot:
	$(PYTHON) verify_all.py --dot
	@echo "Render with: dot -Tpdf flex_paxos_N4.dot -o flex_paxos_N4.pdf"

latex:
	$(PYTHON) verify_all.py --latex

# TLC targets (require Java and tla2tools.jar)
tlc: FlexPaxosGraph.tla PipelinedReconfigOpt.tla AdversarialAdapt.tla
	java -jar $(TLA2TOOLS) -config FlexPaxosGraph_N10.cfg FlexPaxosGraph.tla
	java -jar $(TLA2TOOLS) -config PipelinedReconfigOpt_N10.cfg PipelinedReconfigOpt.tla
	java -jar $(TLA2TOOLS) -config AdversarialAdapt_N10.cfg AdversarialAdapt.tla

# Create .tla symlinks for TLC
%.tla: %.text
	cp $< $@

clean:
	rm -f *.tla *.dot flex_paxos_*.pdf
	rm -rf __pycache__
