import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

class TestCreateOperationExit(unittest.TestCase):
    @patch('setups.get_free_balance_mexc')
    @patch('setups.place_limit_mexc')
    @patch('sqlite3.connect')  # Mock a conexão com SQLite para evitar alterações reais
    def test_operation_exit_normal(self, mock_connect, mock_place_limit_mexc, mock_get_free_balance):
        """Testa uma operação normal sem erros."""
        # Mock resposta da API
        mock_place_limit_mexc.return_value = {'orderId': '12345', 'symbol': 'BTCUSDT'}
        
        # Mock conexão com SQLite
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value.cursor.return_value = mock_cursor
        
        from setups import create_operation_exit
        
        create_operation_exit(
            symbol="BTCUSDT",
            setup_name="Test Setup",
            amount=0.1,
            price=30000,
            exchange="MEXC",
            side="SELL",
            precision=8,
            parent_key="test_parent_key"
        )
        
        # Verifica se a função de cadastro foi chamada
        mock_cursor.execute.assert_called_once()
        self.assertTrue(mock_place_limit_mexc.called)

    @patch('setups.get_free_balance_mexc')
    @patch('setups.place_limit_mexc')
    @patch('sqlite3.connect')
    def test_operation_exit_oversold(self, mock_connect, mock_place_limit_mexc, mock_get_free_balance):
        """Testa uma operação com erro de Oversold e ajuste do saldo."""
        # Simula erro de Oversold na primeira tentativa
        mock_place_limit_mexc.side_effect = [
            {'code': 30005, 'msg': 'Oversold'},  # Primeiro retorno: erro
            {'orderId': '54321', 'symbol': 'BTCUSDT'}  # Segundo retorno: sucesso
        ]
        mock_get_free_balance.return_value = 0.05  # Saldo livre ajustado
        
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value.cursor.return_value = mock_cursor
        
        from setups import create_operation_exit
        
        create_operation_exit(
            symbol="BTCUSDT",
            setup_name="Test Setup",
            amount=0.1,
            price=30000,
            exchange="MEXC",
            side="SELL",
            precision=8,
            parent_key="test_parent_key"
        )
        
        # Verifica se o saldo foi ajustado
        mock_get_free_balance.assert_called_once_with("BTCUSDT")
        self.assertEqual(mock_place_limit_mexc.call_count, 2)  # Duas tentativas de envio
        
        # Verifica se a função de cadastro foi chamada
        mock_cursor.execute.assert_called_once()

    @patch('setups.get_free_balance_mexc')
    @patch('setups.place_limit_mexc')
    @patch('sqlite3.connect')
    def test_operation_exit_no_balance(self, mock_connect, mock_place_limit_mexc, mock_get_free_balance):
        """Testa o caso de Oversold com saldo insuficiente."""
        # Simula erro de Oversold
        mock_place_limit_mexc.side_effect = {'code': 30005, 'msg': 'Oversold'}
        mock_get_free_balance.return_value = 0.0  # Sem saldo
        
        from setups import create_operation_exit
        
        with self.assertRaises(ValueError):  # Verifica se a exceção é levantada
            create_operation_exit(
                symbol="BTCUSDT",
                setup_name="Test Setup",
                amount=0.1,
                price=30000,
                exchange="MEXC",
                side="SELL",
                precision=8,
                parent_key="test_parent_key"
            )
        
        # Verifica se o saldo foi consultado
        mock_get_free_balance.assert_called_once_with("BTCUSDT")

if __name__ == "__main__":
    unittest.main()
03
,