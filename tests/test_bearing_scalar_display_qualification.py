import pytest
from ross_studio.bearing_scalar_qualification import run_scalar_bearing_case


@pytest.mark.parametrize('model',['BallBearingElement','RollerBearingElement'])
def test_scalar_kc_survives_apply_and_reopen(qtbot,tmp_path,model):
    result=run_scalar_bearing_case(model,tmp_path)
    assert result['status']=='PASS'
