import numpy as np
import pytest

from fusion_engine_client.analysis.file_reader import FileReader, MessageData, TimeAlignmentMode
from fusion_engine_client.messages import *
from fusion_engine_client.parsers import FusionEngineEncoder, MixedLogReader


def generate_data(data_path=None, include_binary=False, return_dict=True):
    messages = []

    if include_binary:
        messages.append(b'12345')

    message = EventNotificationMessage()
    message.system_time_ns = 1000000000
    messages.append(message)

    message = PoseMessage()
    message.p1_time = Timestamp(1.0)
    message.velocity_body_mps = np.array([1.0, 2.0, 3.0])
    messages.append(message)

    if include_binary:
        messages.append(b'12345')

    message = PoseMessage()
    message.p1_time = Timestamp(2.0)
    message.velocity_body_mps = np.array([4.0, 5.0, 6.0])
    messages.append(message)

    message = PoseAuxMessage()
    message.p1_time = Timestamp(2.0)
    message.velocity_enu_mps = np.array([14.0, 15.0, 16.0])
    messages.append(message)

    if include_binary:
        messages.append(b'12345')

    message = EventNotificationMessage()
    message.system_time_ns = 3000000000
    messages.append(message)

    message = PoseAuxMessage()
    message.p1_time = Timestamp(3.0)
    message.velocity_enu_mps = np.array([17.0, 18.0, 19.0])
    messages.append(message)

    message = GNSSInfoMessage()
    message.p1_time = Timestamp(2.0)
    message.gdop = 5.0
    messages.append(message)

    if include_binary:
        messages.append(b'12345')

    message = GNSSInfoMessage()
    message.p1_time = Timestamp(3.0)
    message.gdop = 6.0
    messages.append(message)

    message = EventNotificationMessage()
    message.system_time_ns = 4000000000
    messages.append(message)

    if include_binary:
        messages.append(b'12345')

    if data_path is not None:
        encoder = FusionEngineEncoder()
        with open(data_path, 'wb') as f:
            for message in messages:
                if isinstance(message, bytes):
                    f.write(message)
                else:
                    f.write(encoder.encode_message(message))

    if return_dict:
        return message_list_to_dict(messages)
    else:
        return [m for m in messages if not isinstance(m, bytes)]


def message_list_to_dict(messages):
    result = {}
    for message in messages:
        if isinstance(message, bytes):
            continue

        if message.get_type() not in result:
            result[message.get_type()] = MessageData(message.get_type(), None)
        result[message.get_type()].messages.append(message)
    return result


class TestReader:
    @pytest.fixture
    def data_path(self, tmpdir):
        data_path = tmpdir.join('test_file.p1log')
        yield data_path

    def _check_message(self, message, expected_message):
        assert message.get_type() == expected_message.get_type()

        expected_p1_time = expected_message.get_p1_time()
        if expected_p1_time is not None:
            assert float(message.get_p1_time()) == pytest.approx(expected_p1_time, 1e-6)

        expected_system_time_sec = expected_message.get_system_time_sec()
        if expected_system_time_sec is not None:
            assert float(message.get_system_time_sec()) == pytest.approx(expected_system_time_sec, 1e-6)

    def _check_results(self, results, expected_results):
        expected_types = list(expected_results.keys())
        for message_type, message_data in results.items():
            message_data = message_data.messages
            if message_type in expected_types:
                expected_data = expected_results[message_type].messages
                assert len(message_data) == len(expected_data)
                for message, expected_message in zip(message_data, expected_data):
                    self._check_message(message, expected_message)
            else:
                assert len(message_data) == 0

    def test_read_all(self, data_path):
        expected_messages = generate_data(data_path=str(data_path), include_binary=False, return_dict=False)
        expected_result = message_list_to_dict(expected_messages)

        # Construct a reader. This will attempt to set t0 immediately by scanning the data file. If an index file
        # exists, the reader will use the index file to find t0 quickly. If not, it'll read the file directly, but will
        # _not_ attempt to generate an index (which requires reading the entire data file).
        reader = FileReader(path=str(data_path))
        assert reader.t0 is not None
        assert reader.system_t0 is not None
        assert not reader.reader.have_index()

        # Now read the data itself. This _will_ generate an index file.
        result = reader.read()
        self._check_results(result, expected_result)
        assert reader.reader.have_index()
        assert len(reader.reader._original_index) == len(expected_messages)
        assert len(reader.reader.index) == len(expected_messages)

    def test_read_all_with_index(self, data_path):
        expected_messages = generate_data(data_path=str(data_path), include_binary=False, return_dict=False)
        expected_result = message_list_to_dict(expected_messages)

        MixedLogReader.generate_index_file(str(data_path))

        # Construct a reader. We have an index file, so this should use that.
        reader = FileReader(path=str(data_path))
        assert reader.t0 is not None
        assert reader.system_t0 is not None
        assert reader.reader.have_index()

        # Now read the data itself. This will use the index file.
        result = reader.read()
        self._check_results(result, expected_result)

    def test_read_pose(self, data_path):
        messages = generate_data(data_path=str(data_path), include_binary=False, return_dict=False)
        expected_messages = [m for m in messages if isinstance(m, PoseMessage)]
        expected_result = message_list_to_dict(expected_messages)

        # Read just pose messages. This should generate an index for the entire file.
        reader = FileReader(path=str(data_path))
        result = reader.read(message_types=PoseMessage)
        self._check_results(result, expected_result)
        assert reader.reader.have_index()
        assert len(reader.reader._original_index) == len(messages)
        assert len(reader.reader.index) == len(expected_messages)

    def test_read_pose_with_index(self, data_path):
        messages = generate_data(data_path=str(data_path), include_binary=False, return_dict=False)
        expected_messages = [m for m in messages if isinstance(m, PoseMessage)]
        expected_result = message_list_to_dict(expected_messages)

        MixedLogReader.generate_index_file(str(data_path))

        # Just read pose messages. The index file already exists, so we should use that to do the read.
        reader = FileReader(path=str(data_path))
        assert reader.reader.have_index()
        result = reader.read(message_types=PoseMessage)
        self._check_results(result, expected_result)

    def test_read_pose_mixed_binary(self, data_path):
        messages = generate_data(data_path=str(data_path), include_binary=True, return_dict=False)
        expected_messages = [m for m in messages if isinstance(m, PoseMessage)]
        expected_result = message_list_to_dict(expected_messages)

        # Read just pose messages. This should generate an index for the entire file.
        reader = FileReader(path=str(data_path))
        result = reader.read(message_types=PoseMessage)
        self._check_results(result, expected_result)
        assert reader.reader.have_index()
        assert len(reader.reader._original_index) == len(messages)
        assert len(reader.reader.index) == len(expected_messages)

    def test_read_no_generate_index(self, data_path):
        expected_result = generate_data(data_path=str(data_path), include_binary=False)

        # Construct a reader. This will attempt to set t0 immediately by scanning the data file. If an index file
        # exists, the reader will use the index file to find t0 quickly. If not, it'll read the file directly, but will
        # _not_ attempt to generate an index (which requires reading the entire data file).
        reader = FileReader(path=str(data_path))
        assert reader.t0 is not None
        assert reader.system_t0 is not None
        assert not reader.reader.have_index()

        # Now read the data itself. This _will_ generate an index file.
        result = reader.read(generate_index=False)
        self._check_results(result, expected_result)
        assert not reader.reader.have_index()


class TestTimeAlignment:
    @pytest.fixture
    def data(self):
        return generate_data()

    def test_drop(self, data):
        FileReader.time_align_data(data, TimeAlignmentMode.DROP)
        assert len(data[PoseMessage.MESSAGE_TYPE].messages) == 1
        assert float(data[PoseMessage.MESSAGE_TYPE].messages[0].p1_time) == 2.0
        assert len(data[PoseAuxMessage.MESSAGE_TYPE].messages) == 1
        assert float(data[PoseAuxMessage.MESSAGE_TYPE].messages[0].p1_time) == 2.0
        assert len(data[GNSSInfoMessage.MESSAGE_TYPE].messages) == 1
        assert float(data[GNSSInfoMessage.MESSAGE_TYPE].messages[0].p1_time) == 2.0

    def test_insert(self, data):
        FileReader.time_align_data(data, TimeAlignmentMode.INSERT)

        assert len(data[PoseMessage.MESSAGE_TYPE].messages) == 3
        assert float(data[PoseMessage.MESSAGE_TYPE].messages[0].p1_time) == 1.0
        assert float(data[PoseMessage.MESSAGE_TYPE].messages[1].p1_time) == 2.0
        assert float(data[PoseMessage.MESSAGE_TYPE].messages[2].p1_time) == 3.0
        assert data[PoseMessage.MESSAGE_TYPE].messages[0].velocity_body_mps[0] == 1.0
        assert data[PoseMessage.MESSAGE_TYPE].messages[1].velocity_body_mps[0] == 4.0
        assert np.isnan(data[PoseMessage.MESSAGE_TYPE].messages[2].velocity_body_mps[0])

        assert len(data[PoseAuxMessage.MESSAGE_TYPE].messages) == 3
        assert float(data[PoseAuxMessage.MESSAGE_TYPE].messages[0].p1_time) == 1.0
        assert float(data[PoseAuxMessage.MESSAGE_TYPE].messages[1].p1_time) == 2.0
        assert float(data[PoseAuxMessage.MESSAGE_TYPE].messages[2].p1_time) == 3.0
        assert np.isnan(data[PoseAuxMessage.MESSAGE_TYPE].messages[0].velocity_enu_mps[0])
        assert data[PoseAuxMessage.MESSAGE_TYPE].messages[1].velocity_enu_mps[0] == 14.0
        assert data[PoseAuxMessage.MESSAGE_TYPE].messages[2].velocity_enu_mps[0] == 17.0

        assert len(data[GNSSInfoMessage.MESSAGE_TYPE].messages) == 3
        assert float(data[GNSSInfoMessage.MESSAGE_TYPE].messages[0].p1_time) == 1.0
        assert float(data[GNSSInfoMessage.MESSAGE_TYPE].messages[1].p1_time) == 2.0
        assert float(data[GNSSInfoMessage.MESSAGE_TYPE].messages[2].p1_time) == 3.0
        assert np.isnan(data[GNSSInfoMessage.MESSAGE_TYPE].messages[0].gdop)
        assert data[GNSSInfoMessage.MESSAGE_TYPE].messages[1].gdop == 5.0
        assert data[GNSSInfoMessage.MESSAGE_TYPE].messages[2].gdop == 6.0

    def test_specific(self, data):
        FileReader.time_align_data(data, TimeAlignmentMode.DROP,
                                   message_types=[PoseMessage.MESSAGE_TYPE, GNSSInfoMessage.MESSAGE_TYPE])
        assert len(data[PoseMessage.MESSAGE_TYPE].messages) == 1
        assert float(data[PoseMessage.MESSAGE_TYPE].messages[0].p1_time) == 2.0
        assert len(data[PoseAuxMessage.MESSAGE_TYPE].messages) == 2
        assert float(data[PoseAuxMessage.MESSAGE_TYPE].messages[0].p1_time) == 2.0
        assert float(data[PoseAuxMessage.MESSAGE_TYPE].messages[1].p1_time) == 3.0
        assert len(data[GNSSInfoMessage.MESSAGE_TYPE].messages) == 1
        assert float(data[GNSSInfoMessage.MESSAGE_TYPE].messages[0].p1_time) == 2.0
