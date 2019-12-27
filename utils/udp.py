import sys
import pickle
import asyncio


class UdpServer:
    def __init__(self, *args, **kwargs):
        """
        :param local_addr=('127.0.0.1', 9999)
        :param args:
        :param kwargs:
        """
        self.server_protocol_create_params = (args, kwargs)
        self.transport = None
        self.protocol = None

        self._data_receive_q = asyncio.Queue()

    async def start_server(self):
        if self.transport is not None:
            return

        class ServerProtocol(asyncio.Protocol):
            def __init__(self, q: asyncio.Queue):
                self.transport = None
                self.data_receive_q = q

            def connection_made(self, transport):
                self.transport = transport

            def datagram_received(self, data, addr):
                self.data_receive_q.put_nowait((data, addr))

        event_loop = asyncio.get_event_loop()
        args, kw = self.server_protocol_create_params
        self.transport, self.protocol = await event_loop.create_datagram_endpoint(
            lambda: ServerProtocol(self._data_receive_q),
            *args, **kw
        )

    async def sendto(self, data, addr):
        self.transport.sendto(data, addr)

    def received_data_nowait(self):
        return self._data_receive_q.get_nowait()

    async def received_data(self):
        return await self._data_receive_q.get()


class UdpClient:
    def __init__(self, *args, **kwargs):
        """

        :param remote_addr=('127.0.0.1', 9999)
        :param args:
        :param kwargs:
        """
        self.data_receive_q = asyncio.Queue(maxsize=1000)
        self.transport = None
        self.protocol = None
        self.transport_create_params = (args, kwargs)

    async def sendto(self, data):
        if self.transport is None:
            class MyProtocol(asyncio.Protocol):
                def __init__(self, q: asyncio.Queue):
                    self.data_receive_q = q

                def datagram_received(self, d, addr):
                    try:
                        self.data_receive_q.put_nowait((d, addr))
                    except asyncio.queues.QueueFull:
                        sys.stderr.write(f"QueueFull when datagram_received! addr: {addr}, data: {data}")
                        sys.exit(-1)

                def error_received(self, exc):
                    pass

            event_loop = asyncio.get_event_loop()
            args, kwargs = self.transport_create_params
            self.transport, self.protocol = await event_loop.create_datagram_endpoint(
                lambda: MyProtocol(self.data_receive_q),
                *args, **kwargs
            )

        if isinstance(data, str):
            data = data.encode()
        return self.transport.sendto(data)


class UDPSourceToRaffleMQ:
    def __init__(self, host="127.0.0.1", port=40001):
        self.udp_client = UdpClient(remote_addr=(host, port))
        self.udp_server = UdpServer(local_addr=(host, port))

    async def put(self, message):
        py_obj_bytes = pickle.dumps(message)
        await self.udp_client.sendto(py_obj_bytes)

    async def start_listen(self):
        await self.udp_server.start_server()

    def get_nowait(self):
        data, addr = self.udp_server.received_data_nowait()
        return pickle.loads(data)

    async def get(self):
        data, addr = await self.udp_server.received_data()
        return pickle.loads(data)


mq_source_to_raffle = UDPSourceToRaffleMQ()
