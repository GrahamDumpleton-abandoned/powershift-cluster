.PHONY : all

all :

install : all
	pip3 install -U .

package :
	python3 setup.py sdist
	python3 setup.py bdist_wheel --python-tag py3

release : clean package
	twine upload dist/*

clean :
	rm -rf build dist powershift.egg-info
