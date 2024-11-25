from glob import glob
import os.path
import shutil

import pytest

from ScaleHD.align.__alignment import ReferenceIndex


@pytest.fixture(scope='function')
def setUp(request):
    basename = "ref_sample"
    def tearDown():
        shutil.rmtree(basename)
    request.addfinalizer(tearDown)
    return {
        "basename": basename,
    }


def test_reference_index(setUp):
    reference_file = "test/refs/{}.fa".format(setUp["basename"])
    ri = ReferenceIndex(reference_file, target_output="")
    assert os.path.basename(ri.get_index_path()) == os.path.basename(reference_file)
    assert len(glob(ri.get_index_path() + ".*")) == 5
