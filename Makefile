# Define variables for script, input, and output files
SCRIPT = ./to-kalendersiden.py
INPUT_FILE = møder.yaml
OUTPUT_FILE = kalendersiden.txt
TEST_INPUT = test.yaml
TEST_OUTPUT = actual.txt
EXPECTED_OUTPUT = expected.txt

all:	kalendersiden.txt members-example.html members.html 

# Target to generate kalendersiden.txt from møder.yaml
kalendersiden.txt:
	@$(SCRIPT) $(INPUT_FILE) $(OUTPUT_FILE)
	@echo "Generated $(OUTPUT_FILE) from $(INPUT_FILE)."

# Target to run test with test.yaml and compare actual output to expected output
test:
	@$(SCRIPT) $(TEST_INPUT) $(TEST_OUTPUT)
	@echo "Running test: comparing $(EXPECTED_OUTPUT) with $(TEST_OUTPUT)"
	@diff -qZ $(EXPECTED_OUTPUT) $(TEST_OUTPUT) && echo "Test passed!" || echo "Test failed!"

members.html:	members.xlsx
	./visualize-members.py members.xlsx members.html

members-example.html:	members-example.xlsx
	./visualize-members.py members-example.xlsx members-example.html
	
	
httpserver:
	python -m http.server
	
clean:
	rm -f $(OUTPUT_FILE) $(TEST_OUTPUT) members.html 
