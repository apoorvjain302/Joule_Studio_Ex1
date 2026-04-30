@path: '/api'
service AgentProxyService {

  /**
   * Proxy action — forwards the A2A JSON-RPC payload to the
   * EWM Pallet Verification Agent and returns the raw response.
   */
  action verify(
    deliveryOrder : String,
    imageUrl      : String,
    channel       : String default 'web'
  ) returns LargeString;

}
