import os.path
import shutil

import pytest

from ScaleHD.align.__alignment import ReferenceIndex


@pytest.fixture(scope='function')
def setUp_tearDown(request):
    def tearDown():
        shutil.rmtree("4k-HD-INTER")
    request.addfinalizer(tearDown)


def test_reference_index(setUp_tearDown):
    reference_file = "refs/4k-HD-INTER.fa"
    ri = ReferenceIndex(reference_file, target_output="")
    assert os.path.basename(ri.get_index_path()) == os.path.basename(reference_file)
