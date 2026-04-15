import { IsString, IsIn, IsNotEmpty } from 'class-validator';

export class AddMessageDto {
  @IsString()
  @IsNotEmpty()
  id!: string;

  @IsIn(['user', 'assistant', 'system'])
  role!: 'user' | 'assistant' | 'system';

  @IsString()
  @IsNotEmpty()
  content!: string;

  @IsString()
  createdAt!: string;
}
