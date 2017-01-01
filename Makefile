.PHONY : all

all :

install : all
	pip3 install -U .

package :
	python3 setup.py sdist

release : clean package
	twine upload dist/*

clean :
	rm -rf build dist powershift_cluster.egg-info
